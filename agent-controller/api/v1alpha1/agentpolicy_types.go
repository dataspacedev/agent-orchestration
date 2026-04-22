package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// AgentPolicySpec defines the desired state of AgentPolicy.
// It is the namespace-scoped counterpart to ClusterAgentPolicySpec and
// carries identical fields so that per-namespace overrides mirror cluster defaults.
type AgentPolicySpec struct {
	// Auth defines the authentication settings for this namespace.
	// +optional
	Auth AuthSpec `json:"auth,omitempty"`

	// OTEL defines the OpenTelemetry settings for this namespace.
	// +optional
	OTEL OTELSpec `json:"otel,omitempty"`

	// Resilience defines the resilience settings for this namespace.
	// +optional
	Resilience ResilienceSpec `json:"resilience,omitempty"`
}

// AgentPolicyStatus defines the observed state of AgentPolicy.
// Reserved for future conditions.
type AgentPolicyStatus struct{}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Namespaced,shortName=ap

// AgentPolicy is the Schema for the agentpolicies API.
type AgentPolicy struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   AgentPolicySpec   `json:"spec,omitempty"`
	Status AgentPolicyStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// AgentPolicyList contains a list of AgentPolicy.
type AgentPolicyList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []AgentPolicy `json:"items"`
}

func init() {
	SchemeBuilder.Register(&AgentPolicy{}, &AgentPolicyList{})
}
