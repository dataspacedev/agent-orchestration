package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// AgentDirectorySpec defines the desired state of AgentDirectory.
type AgentDirectorySpec struct {
	// AgentName is the canonical name of the agent.
	// +kubebuilder:validation:Required
	AgentName string `json:"agentName"`

	// Version is the semantic version of the agent.
	// +kubebuilder:validation:Required
	Version string `json:"version"`

	// URL is the base URL at which the agent is reachable.
	// +kubebuilder:validation:Required
	URL string `json:"url"`

	// Skills is the list of skill identifiers the agent advertises.
	// +optional
	Skills []string `json:"skills,omitempty"`

	// CardHash is the SHA-256 hash of the agent card JSON, used for integrity checks.
	// +optional
	CardHash string `json:"cardHash,omitempty"`

	// ReadyAt is the timestamp when the agent last became ready.
	// +optional
	ReadyAt *metav1.Time `json:"readyAt,omitempty"`
}

// AgentDirectoryStatus defines the observed state of AgentDirectory.
// Reserved for future conditions.
type AgentDirectoryStatus struct{}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Namespaced,shortName=ad
// +kubebuilder:printcolumn:name="CardHash",type=string,JSONPath=`.spec.cardHash`
// +kubebuilder:printcolumn:name="ReadyAt",type=date,JSONPath=`.spec.readyAt`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// AgentDirectory is the Schema for the agentdirectories API.
type AgentDirectory struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   AgentDirectorySpec   `json:"spec,omitempty"`
	Status AgentDirectoryStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// AgentDirectoryList contains a list of AgentDirectory.
type AgentDirectoryList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []AgentDirectory `json:"items"`
}

func init() {
	SchemeBuilder.Register(&AgentDirectory{}, &AgentDirectoryList{})
}
