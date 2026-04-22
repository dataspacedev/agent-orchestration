package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// AuthSpec defines authentication configuration for an agent policy.
type AuthSpec struct {
	// TokenAudience is the expected audience claim in tokens presented to this agent.
	// +optional
	TokenAudience string `json:"tokenAudience,omitempty"`

	// Mode is the authentication mode (e.g. "jwt", "mtls", "none").
	// +optional
	Mode string `json:"mode,omitempty"`
}

// OTELSpec defines OpenTelemetry configuration for an agent policy.
type OTELSpec struct {
	// Endpoint is the OTLP gRPC/HTTP endpoint to export traces and metrics.
	// +optional
	Endpoint string `json:"endpoint,omitempty"`

	// Sampling is the trace sampling rate in the range [0, 1].
	// +optional
	Sampling float64 `json:"sampling,omitempty"`
}

// ResilienceSpec defines resilience configuration for an agent policy.
type ResilienceSpec struct {
	// TimeoutMs is the per-request timeout in milliseconds.
	// +optional
	TimeoutMs int32 `json:"timeoutMs,omitempty"`

	// Retries is the maximum number of retry attempts on transient failures.
	// +optional
	Retries int32 `json:"retries,omitempty"`
}

// ClusterAgentPolicySpec defines the desired state of ClusterAgentPolicy.
type ClusterAgentPolicySpec struct {
	// Auth defines the authentication settings applied cluster-wide.
	// +optional
	Auth AuthSpec `json:"auth,omitempty"`

	// OTEL defines the OpenTelemetry settings applied cluster-wide.
	// +optional
	OTEL OTELSpec `json:"otel,omitempty"`

	// Resilience defines the resilience settings applied cluster-wide.
	// +optional
	Resilience ResilienceSpec `json:"resilience,omitempty"`
}

// ClusterAgentPolicyStatus defines the observed state of ClusterAgentPolicy.
// Reserved for future conditions.
type ClusterAgentPolicyStatus struct{}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Cluster,shortName=cap

// ClusterAgentPolicy is the Schema for the clusteragentpolicies API.
type ClusterAgentPolicy struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   ClusterAgentPolicySpec   `json:"spec,omitempty"`
	Status ClusterAgentPolicyStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// ClusterAgentPolicyList contains a list of ClusterAgentPolicy.
type ClusterAgentPolicyList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []ClusterAgentPolicy `json:"items"`
}

func init() {
	SchemeBuilder.Register(&ClusterAgentPolicy{}, &ClusterAgentPolicyList{})
}
