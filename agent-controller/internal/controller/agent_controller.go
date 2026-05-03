package controller

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"

	appsv1 "k8s.io/api/apps/v1"
	autoscalingv2 "k8s.io/api/autoscaling/v2"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/intstr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	agentsv1alpha1 "github.com/justinbrewer/agent-orchestration/agent-controller/api/v1alpha1"
)

const (
	defaultPort        = int32(8080)
	defaultMaxReplicas = int32(5)
	defaultMinReplicas = int32(1)
	defaultTargetCPU   = int32(80)
)

// AgentReconciler reconciles an Agent object.
type AgentReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=agents.orchestration.io,resources=agents,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=agents.orchestration.io,resources=agents/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=agents.orchestration.io,resources=agents/finalizers,verbs=update
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=autoscaling,resources=horizontalpodautoscalers,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=serviceaccounts,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=configmaps,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch

func (r *AgentReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	agent := &agentsv1alpha1.Agent{}
	if err := r.Get(ctx, req.NamespacedName, agent); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	if err := r.reconcileServiceAccount(ctx, agent); err != nil {
		if apierrors.IsConflict(err) {
			return ctrl.Result{Requeue: true}, nil
		}
		return r.markDegraded(ctx, agent, "ServiceAccountFailed", err)
	}
	if err := r.reconcileConfigMap(ctx, agent); err != nil {
		if apierrors.IsConflict(err) {
			return ctrl.Result{Requeue: true}, nil
		}
		return r.markDegraded(ctx, agent, "ConfigMapFailed", err)
	}
	if err := r.reconcileDeployment(ctx, agent); err != nil {
		if apierrors.IsConflict(err) {
			return ctrl.Result{Requeue: true}, nil
		}
		return r.markDegraded(ctx, agent, "DeploymentFailed", err)
	}
	if err := r.reconcileService(ctx, agent); err != nil {
		if apierrors.IsConflict(err) {
			return ctrl.Result{Requeue: true}, nil
		}
		return r.markDegraded(ctx, agent, "ServiceFailed", err)
	}
	if err := r.reconcileHPA(ctx, agent); err != nil {
		if apierrors.IsConflict(err) {
			return ctrl.Result{Requeue: true}, nil
		}
		return r.markDegraded(ctx, agent, "HPAFailed", err)
	}

	if err := r.syncStatus(ctx, agent); err != nil {
		logger.Error(err, "failed to sync status")
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

func (r *AgentReconciler) reconcileServiceAccount(ctx context.Context, agent *agentsv1alpha1.Agent) error {
	sa := &corev1.ServiceAccount{
		ObjectMeta: metav1.ObjectMeta{
			Name:      agent.Name,
			Namespace: agent.Namespace,
		},
	}
	_, err := controllerutil.CreateOrUpdate(ctx, r.Client, sa, func() error {
		sa.Labels = resourceLabels(agent)
		return controllerutil.SetControllerReference(agent, sa, r.Scheme)
	})
	return err
}

func (r *AgentReconciler) reconcileConfigMap(ctx context.Context, agent *agentsv1alpha1.Agent) error {
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      configMapName(agent),
			Namespace: agent.Namespace,
		},
	}
	_, err := controllerutil.CreateOrUpdate(ctx, r.Client, cm, func() error {
		cm.Labels = resourceLabels(agent)
		cm.Data = agent.Spec.Config
		return controllerutil.SetControllerReference(agent, cm, r.Scheme)
	})
	return err
}

func (r *AgentReconciler) reconcileDeployment(ctx context.Context, agent *agentsv1alpha1.Agent) error {
	// Validate the referenced Secret exists before creating the Deployment so
	// pods don't enter a crashloop waiting for a missing envFrom source.
	if agent.Spec.SecretName != "" {
		if err := r.validateSecretRef(ctx, agent); err != nil {
			return err
		}
	}

	deploy := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      agent.Name,
			Namespace: agent.Namespace,
		},
	}
	_, err := controllerutil.CreateOrUpdate(ctx, r.Client, deploy, func() error {
		deploy.Labels = resourceLabels(agent)

		// Preserve the replica count managed by the HPA on updates; only set the
		// initial value on creation to avoid fighting the autoscaler.
		var currentReplicas *int32
		if !deploy.CreationTimestamp.IsZero() {
			currentReplicas = deploy.Spec.Replicas
		}

		deploy.Spec = r.buildDeploymentSpec(agent)

		if currentReplicas != nil {
			deploy.Spec.Replicas = currentReplicas
		}

		return controllerutil.SetControllerReference(agent, deploy, r.Scheme)
	})
	return err
}

func (r *AgentReconciler) buildDeploymentSpec(agent *agentsv1alpha1.Agent) appsv1.DeploymentSpec {
	labels := resourceLabels(agent)
	port := agentPort(agent)
	minReplicas := scalingMinReplicas(agent)

	envFrom := []corev1.EnvFromSource{
		{
			ConfigMapRef: &corev1.ConfigMapEnvSource{
				LocalObjectReference: corev1.LocalObjectReference{Name: configMapName(agent)},
			},
		},
	}
	if agent.Spec.SecretName != "" {
		envFrom = append(envFrom, corev1.EnvFromSource{
			SecretRef: &corev1.SecretEnvSource{
				LocalObjectReference: corev1.LocalObjectReference{Name: agent.Spec.SecretName},
			},
		})
	}

	return appsv1.DeploymentSpec{
		Replicas: &minReplicas,
		Selector: &metav1.LabelSelector{MatchLabels: labels},
		Template: corev1.PodTemplateSpec{
			ObjectMeta: metav1.ObjectMeta{
				Labels:      labels,
				Annotations: map[string]string{"config/checksum": configChecksum(agent.Spec.Config)},
			},
			Spec: corev1.PodSpec{
				ServiceAccountName:           agent.Name,
				AutomountServiceAccountToken: ptr(false),
				SecurityContext: &corev1.PodSecurityContext{
					RunAsNonRoot: ptr(true),
					SeccompProfile: &corev1.SeccompProfile{
						Type: corev1.SeccompProfileTypeRuntimeDefault,
					},
				},
				// emptyDir /tmp allows writes under a read-only root filesystem.
				Volumes: []corev1.Volume{
					{
						Name: "tmp",
						VolumeSource: corev1.VolumeSource{
							EmptyDir: &corev1.EmptyDirVolumeSource{},
						},
					},
				},
				Containers: []corev1.Container{
					{
						Name:            "agent",
						Image:           agent.Spec.Image,
						ImagePullPolicy: corev1.PullIfNotPresent,
						Ports: []corev1.ContainerPort{
							{Name: "http", ContainerPort: port, Protocol: corev1.ProtocolTCP},
						},
						EnvFrom:   envFrom,
						Resources: agent.Spec.Resources,
						VolumeMounts: []corev1.VolumeMount{
							{Name: "tmp", MountPath: "/tmp"},
						},
						LivenessProbe: &corev1.Probe{
							ProbeHandler: corev1.ProbeHandler{
								TCPSocket: &corev1.TCPSocketAction{
									Port: intstr.FromInt32(port),
								},
							},
							InitialDelaySeconds: 15,
							PeriodSeconds:       20,
							FailureThreshold:    3,
						},
						ReadinessProbe: &corev1.Probe{
							ProbeHandler: corev1.ProbeHandler{
								TCPSocket: &corev1.TCPSocketAction{
									Port: intstr.FromInt32(port),
								},
							},
							InitialDelaySeconds: 5,
							PeriodSeconds:       10,
							FailureThreshold:    3,
						},
						SecurityContext: &corev1.SecurityContext{
							AllowPrivilegeEscalation: ptr(false),
							ReadOnlyRootFilesystem:   ptr(true),
							RunAsNonRoot:             ptr(true),
							Capabilities: &corev1.Capabilities{
								Drop: []corev1.Capability{"ALL"},
							},
						},
					},
				},
			},
		},
	}
}

func (r *AgentReconciler) reconcileService(ctx context.Context, agent *agentsv1alpha1.Agent) error {
	port := agentPort(agent)
	svc := &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      agent.Name,
			Namespace: agent.Namespace,
		},
	}
	_, err := controllerutil.CreateOrUpdate(ctx, r.Client, svc, func() error {
		svc.Labels = resourceLabels(agent)
		svc.Spec.Selector = resourceLabels(agent)
		svc.Spec.Type = corev1.ServiceTypeClusterIP
		svc.Spec.Ports = []corev1.ServicePort{
			{
				Name:       "http",
				Port:       port,
				TargetPort: intstr.FromInt32(port),
				Protocol:   corev1.ProtocolTCP,
			},
		}
		return controllerutil.SetControllerReference(agent, svc, r.Scheme)
	})
	return err
}

func (r *AgentReconciler) reconcileHPA(ctx context.Context, agent *agentsv1alpha1.Agent) error {
	minReplicas := scalingMinReplicas(agent)

	maxReplicas := agent.Spec.Scaling.MaxReplicas
	if maxReplicas == 0 {
		maxReplicas = defaultMaxReplicas
	}

	targetCPU := defaultTargetCPU
	if agent.Spec.Scaling.TargetCPUUtilizationPercentage != nil {
		targetCPU = *agent.Spec.Scaling.TargetCPUUtilizationPercentage
	}

	hpa := &autoscalingv2.HorizontalPodAutoscaler{
		ObjectMeta: metav1.ObjectMeta{
			Name:      agent.Name,
			Namespace: agent.Namespace,
		},
	}
	_, err := controllerutil.CreateOrUpdate(ctx, r.Client, hpa, func() error {
		hpa.Labels = resourceLabels(agent)
		hpa.Spec = autoscalingv2.HorizontalPodAutoscalerSpec{
			ScaleTargetRef: autoscalingv2.CrossVersionObjectReference{
				APIVersion: "apps/v1",
				Kind:       "Deployment",
				Name:       agent.Name,
			},
			MinReplicas: &minReplicas,
			MaxReplicas: maxReplicas,
			Metrics: []autoscalingv2.MetricSpec{
				{
					Type: autoscalingv2.ResourceMetricSourceType,
					Resource: &autoscalingv2.ResourceMetricSource{
						Name: corev1.ResourceCPU,
						Target: autoscalingv2.MetricTarget{
							Type:               autoscalingv2.UtilizationMetricType,
							AverageUtilization: &targetCPU,
						},
					},
				},
			},
		}
		return controllerutil.SetControllerReference(agent, hpa, r.Scheme)
	})
	return err
}

func (r *AgentReconciler) validateSecretRef(ctx context.Context, agent *agentsv1alpha1.Agent) error {
	secret := &corev1.Secret{}
	err := r.Get(ctx, client.ObjectKey{Name: agent.Spec.SecretName, Namespace: agent.Namespace}, secret)
	if err != nil {
		if apierrors.IsNotFound(err) {
			return fmt.Errorf("referenced secret %q not found in namespace %q", agent.Spec.SecretName, agent.Namespace)
		}
		return fmt.Errorf("failed to look up secret %q: %w", agent.Spec.SecretName, err)
	}
	return nil
}

func (r *AgentReconciler) syncStatus(ctx context.Context, agent *agentsv1alpha1.Agent) error {
	deploy := &appsv1.Deployment{}
	if err := r.Get(ctx, client.ObjectKeyFromObject(agent), deploy); err != nil {
		if apierrors.IsNotFound(err) {
			return nil
		}
		return err
	}

	patch := client.MergeFrom(agent.DeepCopy())
	agent.Status.ReadyReplicas = deploy.Status.ReadyReplicas
	agent.Status.AvailableReplicas = deploy.Status.AvailableReplicas
	agent.Status.ObservedGeneration = agent.Generation

	// Clear any prior Degraded condition now that reconciliation succeeded.
	setCondition(&agent.Status.Conditions, metav1.Condition{
		Type:               agentsv1alpha1.ConditionDegraded,
		Status:             metav1.ConditionFalse,
		Reason:             "ReconciliationSucceeded",
		Message:            "All resources reconciled successfully",
		ObservedGeneration: agent.Generation,
		LastTransitionTime: metav1.Now(),
	})

	readyCond := metav1.Condition{
		Type:               agentsv1alpha1.ConditionReady,
		ObservedGeneration: agent.Generation,
		LastTransitionTime: metav1.Now(),
	}
	if deploy.Status.ReadyReplicas > 0 {
		readyCond.Status = metav1.ConditionTrue
		readyCond.Reason = "DeploymentAvailable"
		readyCond.Message = fmt.Sprintf("%d/%d replicas ready", deploy.Status.ReadyReplicas, deploy.Status.Replicas)
	} else {
		readyCond.Status = metav1.ConditionFalse
		readyCond.Reason = "DeploymentNotReady"
		readyCond.Message = "Waiting for replicas to become ready"
	}
	setCondition(&agent.Status.Conditions, readyCond)

	return r.Status().Patch(ctx, agent, patch)
}

func (r *AgentReconciler) markDegraded(ctx context.Context, agent *agentsv1alpha1.Agent, reason string, reconcileErr error) (ctrl.Result, error) {
	logger := log.FromContext(ctx)
	logger.Error(reconcileErr, "reconciliation failed", "reason", reason)

	patch := client.MergeFrom(agent.DeepCopy())
	setCondition(&agent.Status.Conditions, metav1.Condition{
		Type:               agentsv1alpha1.ConditionDegraded,
		Status:             metav1.ConditionTrue,
		Reason:             reason,
		Message:            reconcileErr.Error(),
		ObservedGeneration: agent.Generation,
		LastTransitionTime: metav1.Now(),
	})

	if err := r.Status().Patch(ctx, agent, patch); err != nil {
		logger.Error(err, "failed to patch degraded status")
	}
	return ctrl.Result{}, reconcileErr
}

// SetupWithManager registers the controller with the Manager and establishes
// ownership watches for all managed resource types. Changes to any owned
// resource re-queue the parent Agent for reconciliation.
func (r *AgentReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&agentsv1alpha1.Agent{}).
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Service{}).
		Owns(&corev1.ServiceAccount{}).
		Owns(&corev1.ConfigMap{}).
		Owns(&autoscalingv2.HorizontalPodAutoscaler{}).
		Complete(r)
}

// resourceLabels returns the standard labels applied to all resources owned by an Agent.
func resourceLabels(agent *agentsv1alpha1.Agent) map[string]string {
	return map[string]string{
		"app.kubernetes.io/name":       "agent",
		"app.kubernetes.io/instance":   agent.Name,
		"app.kubernetes.io/managed-by": "agent-controller",
	}
}

func configMapName(agent *agentsv1alpha1.Agent) string {
	return agent.Name + "-config"
}

func configChecksum(config map[string]string) string {
	keys := make([]string, 0, len(config))
	for k := range config {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	ordered := make([][2]string, len(keys))
	for i, k := range keys {
		ordered[i] = [2]string{k, config[k]}
	}
	b, _ := json.Marshal(ordered)
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:8])
}

func agentPort(agent *agentsv1alpha1.Agent) int32 {
	if agent.Spec.Port != 0 {
		return agent.Spec.Port
	}
	return defaultPort
}

func scalingMinReplicas(agent *agentsv1alpha1.Agent) int32 {
	if agent.Spec.Scaling.MinReplicas != nil {
		return *agent.Spec.Scaling.MinReplicas
	}
	return defaultMinReplicas
}

// setCondition upserts a condition, preserving LastTransitionTime when the
// condition status has not changed.
func setCondition(conditions *[]metav1.Condition, condition metav1.Condition) {
	for i, c := range *conditions {
		if c.Type == condition.Type {
			if c.Status == condition.Status {
				condition.LastTransitionTime = c.LastTransitionTime
			}
			(*conditions)[i] = condition
			return
		}
	}
	*conditions = append(*conditions, condition)
}

func ptr[T any](v T) *T {
	return &v
}
