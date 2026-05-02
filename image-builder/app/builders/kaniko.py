"""KanikoBuilder — dispatches kubernetes BatchV1 Jobs using kaniko."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException

from app.builders.abc import Builder
from app.db.models.build_job import BuildJob
from app.models.build import (
    BuildRequest,
    GitSource,
    InlineSource,
    NodeRuntime,
    PythonRuntime,
    RawRuntime,
)

logger = logging.getLogger(__name__)


def _generate_dockerfile(request: BuildRequest) -> str | None:
    """Return a Dockerfile string for generated runtimes, or None for RawRuntime."""
    rt = request.runtime
    if isinstance(rt, PythonRuntime):
        packages = " ".join(rt.packages) if rt.packages else ""
        lines = [f"FROM python:{rt.version}"]
        if packages:
            lines.append(f"RUN pip install {packages}")
        return "\n".join(lines)
    if isinstance(rt, NodeRuntime):
        packages = " ".join(rt.packages) if rt.packages else ""
        lines = [f"FROM node:{rt.version}"]
        if packages:
            lines.append(f"RUN npm install -g {packages}")
        return "\n".join(lines)
    if isinstance(rt, RawRuntime):
        return None  # caller uses rt.dockerfile directly
    return None  # unreachable


class KanikoBuilder(Builder):
    """Image builder that creates Kubernetes BatchV1 Jobs using kaniko."""

    def __init__(
        self,
        namespace: str,
        kaniko_image: str,
        builder_namespace: str,
        in_cluster: bool = True,
        k8s_api_client: ApiClient | None = None,
    ) -> None:
        self._namespace = namespace
        self._kaniko_image = kaniko_image
        self._builder_namespace = builder_namespace
        self._in_cluster = in_cluster
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

        source = request.source
        if isinstance(source, GitSource):
            git_context = f"git+{source.url}#{source.ref}"
            if source.subpath:
                git_context += f"/{source.subpath}"
            kaniko_args.append(f"--context={git_context}")
        elif isinstance(source, InlineSource):
            kaniko_args.append("--context=tar:///workspace/context.tar.gz")

        # ── ConfigMap for generated Dockerfiles ───────────────────────────────
        volumes: list[dict[str, Any]] = []
        volume_mounts: list[dict[str, Any]] = []

        if generated_dockerfile is not None:
            cm_name = f"image-builder-{job_id}-dockerfile"
            core_api = client.CoreV1Api(self._api_client)
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=cm_name,
                    namespace=self._builder_namespace,
                ),
                data={"Dockerfile": dockerfile_content},
            )
            await core_api.create_namespaced_config_map(
                namespace=self._builder_namespace,
                body=configmap,
            )
            volumes.append({
                "name": "dockerfile",
                "configMap": {"name": cm_name},
            })
            volume_mounts.append({
                "name": "dockerfile",
                "mountPath": "/workspace/Dockerfile",
                "subPath": "Dockerfile",
            })
            kaniko_args.append("--dockerfile=/workspace/Dockerfile")

        # ── Secret for inline source content ──────────────────────────────────
        if isinstance(source, InlineSource):
            secret_name = f"image-builder-{job_id}-context"
            core_api = client.CoreV1Api(self._api_client)
            secret = client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=secret_name,
                    namespace=self._builder_namespace,
                ),
                data={"context.tar.gz": source.content},
            )
            await core_api.create_namespaced_secret(
                namespace=self._builder_namespace,
                body=secret,
            )
            volumes.append({
                "name": "context",
                "secret": {"secretName": secret_name},
            })
            volume_mounts.append({
                "name": "context",
                "mountPath": "/workspace/context.tar.gz",
                "subPath": "context.tar.gz",
            })

        # ── Job spec ──────────────────────────────────────────────────────────
        k8s_volume_mounts = (
            [
                client.V1VolumeMount(
                    name=vm["name"],
                    mount_path=vm["mountPath"],
                    sub_path=vm.get("subPath"),
                )
                for vm in volume_mounts
            ]
            if volume_mounts
            else None
        )
        container = client.V1Container(
            name="kaniko",
            image=self._kaniko_image,
            args=kaniko_args,
            volume_mounts=k8s_volume_mounts,
        )
        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Never",
            volumes=[client.V1Volume(**v) for v in volumes] if volumes else None,
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
