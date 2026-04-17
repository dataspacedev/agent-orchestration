package v1alpha1

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// AgentSpec defines the desired state of Agent.
type AgentSpec struct {
	// Image is the container image for the agent.
	// +kubebuilder:validation:Required
	Image string `json:"image"`

	// Resources defines the compute resource requirements for the agent container.
	// +optional
	Resources corev1.ResourceRequirements `json:"resources,omitempty"`

	// Config holds non-sensitive key-value pairs injected as environment variables
	// via a managed ConfigMap.
	// +optional
	Config map[string]string `json:"config,omitempty"`

	// SecretName references an existing Secret in the same namespace whose keys
	// are injected as environment variables. Sensitive values must be stored in a
	// Secret rather than in Config.
	// +optional
	SecretName string `json:"secretName,omitempty"`

	// Scaling defines the HorizontalPodAutoscaler configuration.
	// +optional
	Scaling ScalingSpec `json:"scaling,omitempty"`

	// Port is the port the agent container listens on. Defaults to 8080.
	// +kubebuilder:default=8080
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=65535
	// +optional
	Port int32 `json:"port,omitempty"`
}

// ScalingSpec defines the HorizontalPodAutoscaler configuration for an Agent.
type ScalingSpec struct {
	// MinReplicas is the lower limit for the number of replicas.
	// +kubebuilder:default=1
	// +kubebuilder:validation:Minimum=1
	// +optional
	MinReplicas *int32 `json:"minReplicas,omitempty"`

	// MaxReplicas is the upper limit for the number of replicas.
	// +kubebuilder:default=5
	// +kubebuilder:validation:Minimum=1
	// +optional
	MaxReplicas int32 `json:"maxReplicas,omitempty"`

	// TargetCPUUtilizationPercentage is the target average CPU utilization across
	// all pods, expressed as a percentage of the requested CPU.
	// +kubebuilder:default=80
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=100
	// +optional
	TargetCPUUtilizationPercentage *int32 `json:"targetCPUUtilizationPercentage,omitempty"`
}

// AgentStatus defines the observed state of Agent.
type AgentStatus struct {
	// Conditions represent the latest available observations of the Agent's state.
	// +optional
	// +listType=map
	// +listMapKey=type
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// ReadyReplicas is the number of pods targeted by this Agent with a Ready condition.
	// +optional
	ReadyReplicas int32 `json:"readyReplicas,omitempty"`

	// AvailableReplicas is the total number of available pods targeted by this Agent.
	// +optional
	AvailableReplicas int32 `json:"availableReplicas,omitempty"`

	// ObservedGeneration is the most recent generation observed by the controller.
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`
}

// Condition type constants.
const (
	ConditionReady    = "Ready"
	ConditionDegraded = "Degraded"
)

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Namespaced,shortName=ag
// +kubebuilder:printcolumn:name="Image",type=string,JSONPath=`.spec.image`
// +kubebuilder:printcolumn:name="Ready",type=integer,JSONPath=`.status.readyReplicas`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// Agent is the Schema for the agents API.
type Agent struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   AgentSpec   `json:"spec,omitempty"`
	Status AgentStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// AgentList contains a list of Agent.
type AgentList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Agent `json:"items"`
}

func init() {
	SchemeBuilder.Register(&Agent{}, &AgentList{})
}
