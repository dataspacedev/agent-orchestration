"""KanikoBuilder — dispatches kubernetes BatchV1 Jobs using kaniko."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException

from app.builders.abc import Builder
from app.db.models.build_job import BuildJob
from app.models.build import (
    BuildRequest,
    ContainerConfig,
    GitSource,
    InlineSource,
    NodeRuntime,
    PythonRuntime,
    RawRuntime,
)

logger = logging.getLogger(__name__)


def _apply_container_config(lines: list[str], cfg: ContainerConfig) -> None:
    """Append ContainerConfig directives to an in-progress Dockerfile line list."""
    for key, value in cfg.env.items():
        lines.append(f"ENV {key}={value!r}")
    for port in cfg.expose:
        lines.append(f"EXPOSE {port}")
    for key, value in cfg.labels.items():
        lines.append(f'LABEL {key}="{value}"')
    if cfg.user:
        lines.append(f"USER {cfg.user}")
    if cfg.entrypoint is not None:
        lines.append(f"ENTRYPOINT {json.dumps(cfg.entrypoint)}")
    if cfg.cmd is not None:
        lines.append(f"CMD {json.dumps(cfg.cmd)}")


def _generate_dockerfile(request: BuildRequest) -> str | None:
    """Return a Dockerfile string for generated runtimes, or None for RawRuntime."""
    rt = request.runtime
    cfg = request.container

    if isinstance(rt, RawRuntime):
        return None  # caller uses rt.dockerfile directly

    if isinstance(rt, PythonRuntime):
        lines = [f"FROM python:{rt.version}-slim"]
        lines.append(f"WORKDIR {cfg.workdir}")
        lines.append("COPY . .")
        if rt.packages:
            lines.append(f"RUN pip install --no-cache-dir {' '.join(rt.packages)}")
    elif isinstance(rt, NodeRuntime):
        lines = [f"FROM node:{rt.version}-slim"]
        lines.append(f"WORKDIR {cfg.workdir}")
        lines.append("COPY . .")
        if rt.packages:
            lines.append(f"RUN npm install {' '.join(rt.packages)}")
    else:
        return None  # unreachable

    _apply_container_config(lines, cfg)
    return "\n".join(lines)


class KanikoBuilder(Builder):
    """Image builder that creates Kubernetes BatchV1 Jobs using kaniko."""

    def __init__(
        self,
        namespace: str,
        kaniko_image: str,
        builder_namespace: str,
        in_cluster: bool = True,
        registry_secret: str | None = None,
        registry_insecure: bool = False,
        build_timeout: float = 600.0,
        build_poll_interval: float = 5.0,
        k8s_api_client: ApiClient | None = None,
    ) -> None:
        self._namespace = namespace
        self._kaniko_image = kaniko_image
        self._builder_namespace = builder_namespace
        self._in_cluster = in_cluster
        self._registry_secret = registry_secret
        self._registry_insecure = registry_insecure
        self._build_timeout = build_timeout
        self._build_poll_interval = build_poll_interval
        # If an external ApiClient is injected (e.g. in tests), use it directly.
        self._api_client: ApiClient | None = k8s_api_client

    async def setup(self) -> None:
        """Initialise the Kubernetes API client."""
        if self._api_client is not None:
            # Already injected (e.g. in tests).
            return
        try:
            if self._in_cluster:
                config.load_incluster_config()  # type: ignore[no-untyped-call]
            else:
                await config.load_kube_config()
            self._api_client = ApiClient()
            logger.info(
                "KanikoBuilder K8s client initialised (builder_namespace=%s)",
                self._builder_namespace,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("K8s config unavailable, builds disabled: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self._api_client is not None

    async def close(self) -> None:
        """Close the Kubernetes API client connection."""
        if self._api_client:
            await self._api_client.close()
            self._api_client = None

    # ── Builder ABC ────────────────────────────────────────────────────────────

    async def build(self, request: BuildRequest, db_job: BuildJob) -> None:  # type: ignore[override]
        """Create a kaniko Kubernetes Job for the given build request.

        Updates *db_job.status* and *db_job.k8s_job_name* in place.
        """
        if not self.is_ready:
            raise RuntimeError("KanikoBuilder not initialised — call setup() first")

        job_id = db_job.id
        job_name = f"image-builder-{job_id}"

        # ── Determine Dockerfile ──────────────────────────────────────────────
        generated_dockerfile = _generate_dockerfile(request)
        runtime = request.runtime
        if generated_dockerfile is None and isinstance(runtime, RawRuntime):
            dockerfile_content = runtime.dockerfile
        else:
            dockerfile_content = generated_dockerfile or ""

        # ── Build kaniko args ─────────────────────────────────────────────────
        kaniko_args: list[str] = [f"--destination={request.image_ref}"]
        if self._registry_insecure:
            kaniko_args.append("--insecure")

        source = request.source
        if isinstance(source, GitSource):
            git_context = f"git+{source.url}#{source.ref}"
            if source.subpath:
                git_context += f"/{source.subpath}"
            kaniko_args.append(f"--context={git_context}")
        elif isinstance(source, InlineSource):
            kaniko_args.append("--context=tar:///workspace/context.tar.gz")

        # ── ConfigMap for generated Dockerfiles ───────────────────────────────
        volumes: list[client.V1Volume] = []
        volume_mounts: list[client.V1VolumeMount] = []

        if generated_dockerfile is not None:
            cm_name = f"image-builder-{job_id}-dockerfile"
            core_api = client.CoreV1Api(self._api_client)
            await core_api.create_namespaced_config_map(
                namespace=self._builder_namespace,
                body=client.V1ConfigMap(
                    metadata=client.V1ObjectMeta(
                        name=cm_name,
                        namespace=self._builder_namespace,
                    ),
                    data={"Dockerfile": dockerfile_content},
                ),
            )
            volumes.append(client.V1Volume(
                name="dockerfile",
                config_map=client.V1ConfigMapVolumeSource(name=cm_name),
            ))
            volume_mounts.append(client.V1VolumeMount(
                name="dockerfile",
                mount_path="/workspace/Dockerfile",
                sub_path="Dockerfile",
            ))
            kaniko_args.append("--dockerfile=/workspace/Dockerfile")

        # ── Secret for inline source content ──────────────────────────────────
        if isinstance(source, InlineSource):
            secret_name = f"image-builder-{job_id}-context"
            core_api = client.CoreV1Api(self._api_client)
            await core_api.create_namespaced_secret(
                namespace=self._builder_namespace,
                body=client.V1Secret(
                    metadata=client.V1ObjectMeta(
                        name=secret_name,
                        namespace=self._builder_namespace,
                    ),
                    data={"context.tar.gz": source.content},
                ),
            )
            volumes.append(client.V1Volume(
                name="context",
                secret=client.V1SecretVolumeSource(secret_name=secret_name),
            ))
            volume_mounts.append(client.V1VolumeMount(
                name="context",
                mount_path="/workspace/context.tar.gz",
                sub_path="context.tar.gz",
            ))

        # ── Registry push credentials (omitted for local/unauthenticated testing) ──
        if self._registry_secret:
            volumes.append(client.V1Volume(
                name="registry-credentials",
                secret=client.V1SecretVolumeSource(
                    secret_name=self._registry_secret,
                    items=[client.V1KeyToPath(key=".dockerconfigjson", path="config.json")],
                ),
            ))
            volume_mounts.append(client.V1VolumeMount(
                name="registry-credentials",
                mount_path="/kaniko/.docker/config.json",
                sub_path="config.json",
                read_only=True,
            ))

        # ── Job spec ──────────────────────────────────────────────────────────
        container = client.V1Container(
            name="kaniko",
            image=self._kaniko_image,
            args=kaniko_args,
            volume_mounts=volume_mounts or None,
        )
        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Never",
            volumes=volumes or None,
        )
        job_spec = client.V1JobSpec(
            template=client.V1PodTemplateSpec(spec=pod_spec),
            backoff_limit=0,
        )
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=self._builder_namespace,
            ),
            spec=job_spec,
        )

        batch_api = client.BatchV1Api(self._api_client)
        await batch_api.create_namespaced_job(
            namespace=self._builder_namespace,
            body=job,
        )
        logger.info("Created kaniko Job %s in %s", job_name, self._builder_namespace)

        db_job.status = "running"
        db_job.k8s_job_name = job_name

    async def cancel(self, job_id: str) -> None:
        """Delete the kaniko Job for *job_id*, swallowing 404 errors."""
        if not self.is_ready:
            raise RuntimeError("KanikoBuilder not initialised — call setup() first")

        job_name = f"image-builder-{job_id}"
        batch_api = client.BatchV1Api(self._api_client)
        try:
            await batch_api.delete_namespaced_job(
                name=job_name,
                namespace=self._builder_namespace,
                body=client.V1DeleteOptions(propagation_policy="Foreground"),
            )
            logger.info("Cancelled kaniko Job %s", job_name)
        except ApiException as exc:
            if exc.status != 404:
                raise
            logger.debug("Job %s already absent (cancel is a no-op)", job_name)

    async def wait_for_completion(self, job_id: str) -> bool:
        """Poll the kaniko Job until it succeeds or fails.

        Returns True on success, False on failure or timeout.
        """
        job_name = f"image-builder-{job_id}"
        batch_api = client.BatchV1Api(self._api_client)
        deadline = asyncio.get_event_loop().time() + self._build_timeout

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                logger.warning("Build job %s timed out after %.0fs", job_id, self._build_timeout)
                return False

            try:
                k8s_job = await batch_api.read_namespaced_job(
                    name=job_name,
                    namespace=self._builder_namespace,
                )
            except ApiException as exc:
                if exc.status == 404:
                    logger.warning("Build job %s: K8s Job not found during poll", job_id)
                    return False
                raise

            status = k8s_job.status
            if status.succeeded and status.succeeded > 0:
                logger.info("Build job %s succeeded", job_id)
                return True
            if status.failed and status.failed > 0:
                logger.warning("Build job %s failed (K8s Job backoff exhausted)", job_id)
                return False

            await asyncio.sleep(min(self._build_poll_interval, remaining))

    async def get_logs(self, job_id: str) -> AsyncIterator[str]:
        """Yield log lines from all pods belonging to the kaniko Job for *job_id*."""
        if not self.is_ready:
            raise RuntimeError("KanikoBuilder not initialised — call setup() first")

        job_name = f"image-builder-{job_id}"
        core_api = client.CoreV1Api(self._api_client)
        pod_list = await core_api.list_namespaced_pod(
            namespace=self._builder_namespace,
            label_selector=f"job-name={job_name}",
        )
        for pod in pod_list.items:
            try:
                log_response = await core_api.read_namespaced_pod_log(
                    name=pod.metadata.name,
                    namespace=self._builder_namespace,
                    follow=False,
                )
                for line in log_response.split("\n"):
                    yield line
            except ApiException as exc:
                logger.warning(
                    "Could not retrieve logs for pod %s: %s",
                    pod.metadata.name,
                    exc,
                )
