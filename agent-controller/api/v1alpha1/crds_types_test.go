package v1alpha1_test

import (
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"

	v1alpha1 "github.com/justinbrewer/agent-orchestration/agent-controller/api/v1alpha1"
)

// TestAgentDirectorySpec verifies that AgentDirectorySpec has all required fields
// with the correct types as specified in the CRD design.
func TestAgentDirectorySpec(t *testing.T) {
	spec := v1alpha1.AgentDirectorySpec{
		AgentName: "test-agent",
		Version:   "1.0.0",
		URL:       "https://agent.example.com",
		Skills:    []string{"skill-a", "skill-b"},
		CardHash:  "abc123",
		ReadyAt:   &metav1.Time{},
	}

	if spec.AgentName != "test-agent" {
		t.Errorf("expected AgentName=test-agent, got %s", spec.AgentName)
	}
	if spec.Version != "1.0.0" {
		t.Errorf("expected Version=1.0.0, got %s", spec.Version)
	}
	if spec.URL != "https://agent.example.com" {
		t.Errorf("expected URL=https://agent.example.com, got %s", spec.URL)
	}
	if len(spec.Skills) != 2 {
		t.Errorf("expected 2 skills, got %d", len(spec.Skills))
	}
	if spec.CardHash != "abc123" {
		t.Errorf("expected CardHash=abc123, got %s", spec.CardHash)
	}
	if spec.ReadyAt == nil {
		t.Error("expected ReadyAt to be non-nil")
	}
}

// TestAgentDirectoryIsRuntimeObject verifies AgentDirectory satisfies runtime.Object.
func TestAgentDirectoryIsRuntimeObject(t *testing.T) {
	var _ runtime.Object = &v1alpha1.AgentDirectory{}
	var _ runtime.Object = &v1alpha1.AgentDirectoryList{}
}

// TestClusterAgentPolicySpec verifies ClusterAgentPolicySpec has auth, otel, resilience sub-specs.
func TestClusterAgentPolicySpec(t *testing.T) {
	spec := v1alpha1.ClusterAgentPolicySpec{
		Auth: v1alpha1.AuthSpec{
			TokenAudience: "my-audience",
			Mode:          "jwt",
		},
		OTEL: v1alpha1.OTELSpec{
			Endpoint: "http://otel.example.com:4317",
			Sampling: 0.5,
		},
		Resilience: v1alpha1.ResilienceSpec{
			TimeoutMs: 3000,
			Retries:   3,
		},
	}

	if spec.Auth.TokenAudience != "my-audience" {
		t.Errorf("expected TokenAudience=my-audience, got %s", spec.Auth.TokenAudience)
	}
	if spec.Auth.Mode != "jwt" {
		t.Errorf("expected Mode=jwt, got %s", spec.Auth.Mode)
	}
	if spec.OTEL.Endpoint != "http://otel.example.com:4317" {
		t.Errorf("expected OTEL.Endpoint, got %s", spec.OTEL.Endpoint)
	}
	if spec.OTEL.Sampling != 0.5 {
		t.Errorf("expected Sampling=0.5, got %f", spec.OTEL.Sampling)
	}
	if spec.Resilience.TimeoutMs != 3000 {
		t.Errorf("expected TimeoutMs=3000, got %d", spec.Resilience.TimeoutMs)
	}
	if spec.Resilience.Retries != 3 {
		t.Errorf("expected Retries=3, got %d", spec.Resilience.Retries)
	}
}

// TestClusterAgentPolicyIsRuntimeObject verifies ClusterAgentPolicy satisfies runtime.Object.
func TestClusterAgentPolicyIsRuntimeObject(t *testing.T) {
	var _ runtime.Object = &v1alpha1.ClusterAgentPolicy{}
	var _ runtime.Object = &v1alpha1.ClusterAgentPolicyList{}
}

// TestAgentPolicySpec verifies AgentPolicySpec has identical fields to ClusterAgentPolicySpec.
func TestAgentPolicySpec(t *testing.T) {
	spec := v1alpha1.AgentPolicySpec{
		Auth: v1alpha1.AuthSpec{
			TokenAudience: "ns-audience",
			Mode:          "mtls",
		},
		OTEL: v1alpha1.OTELSpec{
			Endpoint: "http://otel.svc:4317",
			Sampling: 1.0,
		},
		Resilience: v1alpha1.ResilienceSpec{
			TimeoutMs: 5000,
			Retries:   5,
		},
	}

	if spec.Auth.TokenAudience != "ns-audience" {
		t.Errorf("expected TokenAudience=ns-audience, got %s", spec.Auth.TokenAudience)
	}
	if spec.OTEL.Sampling != 1.0 {
		t.Errorf("expected Sampling=1.0, got %f", spec.OTEL.Sampling)
	}
	if spec.Resilience.Retries != 5 {
		t.Errorf("expected Retries=5, got %d", spec.Resilience.Retries)
	}
}

// TestAgentPolicyIsRuntimeObject verifies AgentPolicy satisfies runtime.Object.
func TestAgentPolicyIsRuntimeObject(t *testing.T) {
	var _ runtime.Object = &v1alpha1.AgentPolicy{}
	var _ runtime.Object = &v1alpha1.AgentPolicyList{}
}

// TestSchemeRegistration verifies all new types are registered in the scheme via AddToScheme.
func TestSchemeRegistration(t *testing.T) {
	s := runtime.NewScheme()
	if err := v1alpha1.AddToScheme(s); err != nil {
		t.Fatalf("AddToScheme failed: %v", err)
	}

	// Verify new types are known to the scheme
	types := []runtime.Object{
		&v1alpha1.AgentDirectory{},
		&v1alpha1.AgentDirectoryList{},
		&v1alpha1.ClusterAgentPolicy{},
		&v1alpha1.ClusterAgentPolicyList{},
		&v1alpha1.AgentPolicy{},
		&v1alpha1.AgentPolicyList{},
	}

	for _, obj := range types {
		gvks, _, err := s.ObjectKinds(obj)
		if err != nil {
			t.Errorf("type %T not registered in scheme: %v", obj, err)
			continue
		}
		if len(gvks) == 0 {
			t.Errorf("type %T has no GVKs registered", obj)
		}
	}
}
