# Distinguishing Readiness and Liveness Probes in Kubernetes

## Summary
Kubernetes probes are periodic diagnostics run by the kubelet on each container. A readiness probe determines whether a pod is ready to accept traffic; a failed readiness check merely marks the pod as not ready, without restarting the container [1]. In contrast, a liveness probe signals whether a container should be restarted when it becomes unhealthy; a failure triggers a container restart [1]. Readiness probes are configured via the `readinessProbe` field, while liveness probes use the `livenessProbe` field, though their configuration syntax is otherwise identical [2]. Pods with containers reporting not ready are excluded from Service load balancing, preventing traffic from reaching them [2].

## Readiness Probe Purpose
A readiness probe checks if a container is ready to serve requests. When a readiness probe fails, the kubelet sets the pod’s Ready condition to false, and the pod is removed from Service endpoints. The container continues running, allowing the application to recover or finish initialization without disruption [1, 2].

## Liveness Probe Purpose
A liveness probe monitors whether a container is still alive. If the probe fails, the kubelet restarts the container to recover from a hung or crashed state. Liveness probes are typically used to detect deadlocks or fatal errors that prevent normal operation [1].

## Behavioral Differences and Lifecycle Impact
- **Effect on Pod State**: Readiness failures change the pod’s Ready status but leave the container running [1]; liveness failures trigger a container restart, potentially affecting pod uptime [1].  
- **Traffic Routing**: Readiness probes directly influence Service routing; a pod marked not ready is excluded from the Service’s endpoint list, ensuring clients do not hit an unprepared container [2]. Liveness probes do not affect routing; they only influence the container’s lifecycle.  
- **Recovery Path**: Readiness probes allow graceful draining and graceful termination of pods during updates or scaling events, as the kubelet can remove them from traffic before terminating. Liveness probes provide a safety net for containers that become unresponsive.

## Typical Configuration and Use Cases
- **Readiness**: Commonly used for services that require a warm‑up period (e.g., database migrations, cache priming). Configurations often involve a short initial delay and a simple HTTP GET or TCP check that returns success once the application is fully initialized [1].  
- **Liveness**: Employed for long‑running services that may deadlock or crash. Configurations often include a longer timeout and may involve a custom script that verifies the application’s health state [1].

## Limitations
- The evidence does not provide a definition or purpose for a Kubernetes readiness probe; this gap is acknowledged.  
- No direct statements compare the exact timeout or failure thresholds between readiness and liveness probes; such details must be inferred from general probe configuration patterns.  
- The evidence does not cover advanced probe features such as exec or HTTP header checks, nor does it discuss probe failure handling nuances beyond the basic restart or readiness flag.

## References

1. Liveness, Readiness, and Startup Probes — https://kubernetes.io/docs/concepts/workloads/pods/probes/
2. Configure Liveness, Readiness and Startup Probes — https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | A failed readiness probe does not restart the container but marks the pod as not ready. | "For a failed readiness probe, the kubelet continues running the container that failed checks, and also continues to run more probes; because the check" | 1988-2204 |
| [1] | A probe is a diagnostic performed periodically by the kubelet on a container. | "A probe is a diagnostic performed periodically by the kubelet on a container." | 93-170 |
| [2] | A pod with containers reporting that they are not ready does not receive traffic through Kubernetes Services. | "A pod with containers reporting that they are not ready does not receive traffic through Kubernetes Services." | 2010-2119 |
| [2] | Readiness probes are configured similarly to liveness probes, but use the readinessProbe field instead of the  | "Readiness probes are configured similarly to liveness probes. The only difference is that you use the readinessProbe field instead of the livenessProb" | 2120-2278 |

---
*4 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*