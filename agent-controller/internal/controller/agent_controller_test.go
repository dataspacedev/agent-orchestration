package controller

import (
	"context"
	"testing"

	appsv1 "k8s.io/api/apps/v1"
	autoscalingv2 "k8s.io/api/autoscaling/v2"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	agentsv1alpha1 "github.com/justinbrewer/agent-orchestration/agent-controller/api/v1alpha1"
)

func newTestScheme(t *testing.T) *runtime.Scheme {
	t.Helper()
	s := runtime.NewScheme()
	if err := clientgoscheme.AddToScheme(s); err != nil {
		t.Fatalf("add clientgoscheme: %v", err)
	}
	if err := agentsv1alpha1.AddToScheme(s); err != nil {
		t.Fatalf("add agentsv1alpha1: %v", err)
	}
	return s
}

func newTestAgent(name, namespace string) *agentsv1alpha1.Agent {
	return &agentsv1alpha1.Agent{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
		},
		Spec: agentsv1alpha1.AgentSpec{
			Image: "test-image:latest",
			Resources: corev1.ResourceRequirements{
				Limits: corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("200m"),
					corev1.ResourceMemory: resource.MustParse("256Mi"),
				},
				Requests: corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("50m"),
					corev1.ResourceMemory: resource.MustParse("64Mi"),
				},
			},
			Config: map[string]string{"ENV": "test", "LOG_LEVEL": "info"},
		},
	}
}

func mustReconcile(t *testing.T, r *AgentReconciler, name, namespace string) ctrl.Result {
	t.Helper()
	result, err := r.Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: name, Namespace: namespace},
	})
	if err != nil {
		t.Fatalf("Reconcile returned unexpected error: %v", err)
	}
	return result
}

func TestReconcile_CreatesAllResources(t *testing.T) {
	s := newTestScheme(t)
	agent := newTestAgent("my-agent", "default")

	c := fake.NewClientBuilder().
		WithScheme(s).
		WithObjects(agent).
		WithStatusSubresource(&agentsv1alpha1.Agent{}).
		Build()

	r := &AgentReconciler{Client: c, Scheme: s}
	mustReconcile(t, r, "my-agent", "default")

	ctx := context.Background()
	key := types.NamespacedName{Name: "my-agent", Namespace: "default"}

	// Deployment
	deploy := &appsv1.Deployment{}
	if err := c.Get(ctx, key, deploy); err != nil {
		t.Fatalf("expected Deployment to be created: %v", err)
	}
	container := deploy.Spec.Template.Spec.Containers[0]
	if container.Image != "test-image:latest" {
		t.Errorf("unexpected image %q", container.Image)
	}
	if container.SecurityContext.ReadOnlyRootFilesystem == nil || !*container.SecurityContext.ReadOnlyRootFilesystem {
		t.Error("expected ReadOnlyRootFilesystem=true")
	}
	if container.SecurityContext.AllowPrivilegeEscalation == nil || *container.SecurityContext.AllowPrivilegeEscalation {
		t.Error("expected AllowPrivilegeEscalation=false")
	}
	if len(container.SecurityContext.Capabilities.Drop) == 0 {
		t.Error("expected capabilities.drop to be set")
	}
	if deploy.Spec.Template.Spec.AutomountServiceAccountToken == nil || *deploy.Spec.Template.Spec.AutomountServiceAccountToken {
		t.Error("expected AutomountServiceAccountToken=false")
	}

	// Service
	svc := &corev1.Service{}
	if err := c.Get(ctx, key, svc); err != nil {
		t.Fatalf("expected Service to be created: %v", err)
	}
	if svc.Spec.Type != corev1.ServiceTypeClusterIP {
		t.Errorf("expected ClusterIP, got %s", svc.Spec.Type)
	}
	if len(svc.Spec.Ports) != 1 || svc.Spec.Ports[0].Port != defaultPort {
		t.Errorf("unexpected service ports: %v", svc.Spec.Ports)
	}

	// ServiceAccount
	sa := &corev1.ServiceAccount{}
	if err := c.Get(ctx, key, sa); err != nil {
		t.Fatalf("expected ServiceAccount to be created: %v", err)
	}

	// ConfigMap
	cm := &corev1.ConfigMap{}
	if err := c.Get(ctx, types.NamespacedName{Name: "my-agent-config", Namespace: "default"}, cm); err != nil {
		t.Fatalf("expected ConfigMap to be created: %v", err)
	}
	if cm.Data["ENV"] != "test" || cm.Data["LOG_LEVEL"] != "info" {
		t.Errorf("unexpected ConfigMap data: %v", cm.Data)
	}

	// HPA
	hpa := &autoscalingv2.HorizontalPodAutoscaler{}
	if err := c.Get(ctx, key, hpa); err != nil {
		t.Fatalf("expected HPA to be created: %v", err)
	}
	if hpa.Spec.MaxReplicas != defaultMaxReplicas {
		t.Errorf("expected MaxReplicas=%d, got %d", defaultMaxReplicas, hpa.Spec.MaxReplicas)
	}
	if *hpa.Spec.MinReplicas != defaultMinReplicas {
		t.Errorf("expected MinReplicas=%d, got %d", defaultMinReplicas, *hpa.Spec.MinReplicas)
	}
	if *hpa.Spec.Metrics[0].Resource.Target.AverageUtilization != defaultTargetCPU {
		t.Errorf("expected targetCPU=%d, got %d", defaultTargetCPU, *hpa.Spec.Metrics[0].Resource.Target.AverageUtilization)
	}
}

func TestReconcile_CustomPort(t *testing.T) {
	s := newTestScheme(t)
	agent := newTestAgent("port-agent", "default")
	agent.Spec.Port = 9090

	c := fake.NewClientBuilder().
		WithScheme(s).
		WithObjects(agent).
		WithStatusSubresource(&agentsv1alpha1.Agent{}).
		Build()

	mustReconcile(t, &AgentReconciler{Client: c, Scheme: s}, "port-agent", "default")

	svc := &corev1.Service{}
	if err := c.Get(context.Background(), types.NamespacedName{Name: "port-agent", Namespace: "default"}, svc); err != nil {
		t.Fatalf("expected Service: %v", err)
	}
	if svc.Spec.Ports[0].Port != 9090 {
		t.Errorf("expected port 9090, got %d", svc.Spec.Ports[0].Port)
	}
}

func TestReconcile_CustomScaling(t *testing.T) {
	s := newTestScheme(t)
	agent := newTestAgent("scale-agent", "default")
	minReplicas := int32(2)
	targetCPU := int32(60)
	agent.Spec.Scaling = agentsv1alpha1.ScalingSpec{
		MinReplicas:                    &minReplicas,
		MaxReplicas:                    10,
		TargetCPUUtilizationPercentage: &targetCPU,
	}

	c := fake.NewClientBuilder().
		WithScheme(s).
		WithObjects(agent).
		WithStatusSubresource(&agentsv1alpha1.Agent{}).
		Build()

	mustReconcile(t, &AgentReconciler{Client: c, Scheme: s}, "scale-agent", "default")

	hpa := &autoscalingv2.HorizontalPodAutoscaler{}
	if err := c.Get(context.Background(), types.NamespacedName{Name: "scale-agent", Namespace: "default"}, hpa); err != nil {
		t.Fatalf("expected HPA: %v", err)
	}
	if *hpa.Spec.MinReplicas != 2 {
		t.Errorf("expected MinReplicas=2, got %d", *hpa.Spec.MinReplicas)
	}
	if hpa.Spec.MaxReplicas != 10 {
		t.Errorf("expected MaxReplicas=10, got %d", hpa.Spec.MaxReplicas)
	}
	if *hpa.Spec.Metrics[0].Resource.Target.AverageUtilization != 60 {
		t.Errorf("expected targetCPU=60, got %d", *hpa.Spec.Metrics[0].Resource.Target.AverageUtilization)
	}
}

func TestReconcile_SecretRef_Missing(t *testing.T) {
	s := newTestScheme(t)
	agent := newTestAgent("secret-agent", "default")
	agent.Spec.SecretName = "missing-secret"

	c := fake.NewClientBuilder().
		WithScheme(s).
		WithObjects(agent).
		WithStatusSubresource(&agentsv1alpha1.Agent{}).
		Build()

	_, err := (&AgentReconciler{Client: c, Scheme: s}).Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "secret-agent", Namespace: "default"},
	})
	if err == nil {
		t.Fatal("expected error for missing secret, got nil")
	}
}

func TestReconcile_SecretRef_Present(t *testing.T) {
	s := newTestScheme(t)
	agent := newTestAgent("secret-agent", "default")
	agent.Spec.SecretName = "my-secret"

	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: "my-secret", Namespace: "default"},
	}

	c := fake.NewClientBuilder().
		WithScheme(s).
		WithObjects(agent, secret).
		WithStatusSubresource(&agentsv1alpha1.Agent{}).
		Build()

	mustReconcile(t, &AgentReconciler{Client: c, Scheme: s}, "secret-agent", "default")

	deploy := &appsv1.Deployment{}
	if err := c.Get(context.Background(), types.NamespacedName{Name: "secret-agent", Namespace: "default"}, deploy); err != nil {
		t.Fatalf("expected Deployment: %v", err)
	}
	envFrom := deploy.Spec.Template.Spec.Containers[0].EnvFrom
	if len(envFrom) != 2 {
		t.Errorf("expected 2 envFrom sources (ConfigMap + Secret), got %d", len(envFrom))
	}
}

func TestReconcile_AgentNotFound(t *testing.T) {
	s := newTestScheme(t)
	c := fake.NewClientBuilder().WithScheme(s).Build()

	result, err := (&AgentReconciler{Client: c, Scheme: s}).Reconcile(context.Background(), ctrl.Request{
		NamespacedName: types.NamespacedName{Name: "nonexistent", Namespace: "default"},
	})
	if err != nil {
		t.Fatalf("expected no error for missing Agent, got: %v", err)
	}
	if result.Requeue {
		t.Error("expected no requeue for missing Agent")
	}
}

func TestSetCondition_AddAndUpdate(t *testing.T) {
	conditions := []metav1.Condition{}

	setCondition(&conditions, metav1.Condition{
		Type:   agentsv1alpha1.ConditionReady,
		Status: metav1.ConditionFalse,
		Reason: "NotReady",
	})
	if len(conditions) != 1 {
		t.Fatalf("expected 1 condition, got %d", len(conditions))
	}

	// Status change — LastTransitionTime must be updated.
	setCondition(&conditions, metav1.Condition{
		Type:               agentsv1alpha1.ConditionReady,
		Status:             metav1.ConditionTrue,
		Reason:             "Ready",
		LastTransitionTime: metav1.Now(),
	})
	if conditions[0].Status != metav1.ConditionTrue {
		t.Error("expected condition status True after update")
	}

	// No status change — LastTransitionTime must be preserved.
	saved := conditions[0].LastTransitionTime
	setCondition(&conditions, metav1.Condition{
		Type:   agentsv1alpha1.ConditionReady,
		Status: metav1.ConditionTrue,
		Reason: "StillReady",
	})
	if conditions[0].LastTransitionTime != saved {
		t.Error("expected LastTransitionTime to be preserved when status unchanged")
	}
	if len(conditions) != 1 {
		t.Errorf("expected 1 condition after upsert, got %d", len(conditions))
	}
}

func TestResourceLabels(t *testing.T) {
	agent := newTestAgent("foo", "bar")
	labels := resourceLabels(agent)
	if labels["app.kubernetes.io/instance"] != "foo" {
		t.Errorf("unexpected instance label: %v", labels)
	}
	if labels["app.kubernetes.io/managed-by"] != "agent-controller" {
		t.Errorf("unexpected managed-by label: %v", labels)
	}
}
