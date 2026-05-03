import logging
import re
from typing import Any

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.client.exceptions import ApiException

logger = logging.getLogger(__name__)

_GROUP = "agents.orchestration.io"
_VERSION = "v1alpha1"
_PLURAL = "agents"


def make_crd_name(name: str, version: str) -> str:
    raw = f"{name}-{version}".lower()
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")


def _build_crd_spec(spec: dict[str, Any]) -> dict[str, Any]:
    crd_spec: dict[str, Any] = {"image": spec["image"]}
    if spec.get("port"):
        crd_spec["port"] = spec["port"]
    if spec.get("secret_name"):
        crd_spec["secretName"] = spec["secret_name"]
    if spec.get("config"):
        crd_spec["config"] = spec["config"]
    if spec.get("resources"):
        r = spec["resources"]
        res: dict[str, Any] = {}
        if r.get("requests"):
            res["requests"] = r["requests"]
        if r.get("limits"):
            res["limits"] = r["limits"]
        if res:
            crd_spec["resources"] = res
    if spec.get("scaling"):
        s = spec["scaling"]
        scaling: dict[str, Any] = {}
        if s.get("min_replicas") is not None:
            scaling["minReplicas"] = s["min_replicas"]
        if s.get("max_replicas") is not None:
            scaling["maxReplicas"] = s["max_replicas"]
        if s.get("target_cpu_utilization_percentage") is not None:
            scaling["targetCPUUtilizationPercentage"] = s["target_cpu_utilization_percentage"]
        if scaling:
            crd_spec["scaling"] = scaling
    return crd_spec


class K8sAgentClient:
    def __init__(self, namespace: str, in_cluster: bool = True) -> None:
        self._namespace = namespace
        self._in_cluster = in_cluster
        self._api_client: ApiClient | None = None

    async def setup(self) -> None:
        try:
            if self._in_cluster:
                config.load_incluster_config()
            else:
                await config.load_kube_config()
            self._api_client = ApiClient()
            logger.info("K8s client initialized (namespace=%s)", self._namespace)
        except Exception as exc:
            logger.warning("K8s config unavailable, CRD sync disabled: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self._api_client is not None

    async def close(self) -> None:
        if self._api_client:
            await self._api_client.close()

    def _custom_api(self) -> client.CustomObjectsApi:
        return client.CustomObjectsApi(self._api_client)

    async def apply(self, crd_name: str, spec_payload: dict[str, Any]) -> None:
        if not self.is_ready:
            raise RuntimeError("K8s client not initialized")
        body = {
            "apiVersion": f"{_GROUP}/{_VERSION}",
            "kind": "Agent",
            "metadata": {"name": crd_name, "namespace": self._namespace},
            "spec": _build_crd_spec(spec_payload),
        }
        api = self._custom_api()
        try:
            await api.create_namespaced_custom_object(
                group=_GROUP,
                version=_VERSION,
                namespace=self._namespace,
                plural=_PLURAL,
                body=body,
            )
            logger.info("created Agent CRD %s", crd_name)
        except ApiException as exc:
            if exc.status != 409:
                raise
            await api.patch_namespaced_custom_object(
                group=_GROUP,
                version=_VERSION,
                namespace=self._namespace,
                plural=_PLURAL,
                name=crd_name,
                body=body,
            )
            logger.info("patched Agent CRD %s", crd_name)

    async def delete(self, crd_name: str) -> None:
        if not self.is_ready:
            raise RuntimeError("K8s client not initialized")
        api = self._custom_api()
        try:
            await api.delete_namespaced_custom_object(
                group=_GROUP,
                version=_VERSION,
                namespace=self._namespace,
                plural=_PLURAL,
                name=crd_name,
            )
            logger.info("deleted Agent CRD %s", crd_name)
        except ApiException as exc:
            if exc.status != 404:
                raise
            logger.debug("Agent CRD %s already absent", crd_name)
