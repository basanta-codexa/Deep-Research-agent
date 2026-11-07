# Idempotent HTTP Methods and Their Role in Request Retries

## Summary
Idempotency means that repeated identical requests produce the same server state as a single request. The HTTP specification marks all safe methods, PUT, and DELETE as idempotent. This property is critical when clients retry requests, ensuring no unintended side effects. Understanding which methods are idempotent helps design reliable APIs. [1, 2]

## Definition of Idempotency
An HTTP method is idempotent if the intended effect on the server of making a single request is the same as the effect of making several identical requests. [1]

## Idempotent Methods per the Specification
According to the specification, all safe methods are idempotent, as are PUT and DELETE. [1] Safe methods include those that do not modify server state, such as GET, HEAD, OPTIONS, and TRACE. (Note: the evidence confirms the grouping but does not enumerate each method.) [1]

## Importance of Idempotency for Retries
When a client retries a request, idempotent methods guarantee that the repeated operation will not alter the server state beyond the initial effect. This prevents duplicate resource creation, unintended deletions, or inconsistent data. Idempotency is therefore one of the most important concepts when designing reliable HTTP APIs. [2]

## Practical Implications
- **Safe Methods**: Retries of GET, HEAD, OPTIONS, or TRACE are always safe because they do not change state. [1]
- **PUT**: Re‑sending a PUT request updates the resource to the same representation, leaving the state unchanged after the first successful update. [1]
- **DELETE**: Re‑sending a DELETE request has no additional effect once the resource is removed. [1]
- **Non‑Idempotent Methods**: Methods like POST may create new resources or trigger side effects on each retry, making retries risky. (Evidence does not cover POST, so this is a general caution.) [2]

## Limitations
- The evidence does not list every safe method explicitly; it only states that all safe methods are idempotent. [1]
- The evidence does not discuss other methods (e.g., PATCH, CONNECT, TRACE) beyond the grouping of safe methods. [1]
- The importance of idempotency is asserted in a general sense; specific retry strategies are not detailed. [2]

## References

1. Idempotent — https://developer.mozilla.org/en-US/docs/Glossary/Idempotent
2. DevToolsHub — Free Developer Tools — https://devtoolshub.net/blog/idempotent-http-requests

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | All safe methods are idempotent, as well as PUT and DELETE. | "All safe methods are idempotent, as well as PUT and DELETE." | 632-691 |
| [1] | An HTTP method is idempotent if the intended effect on the server of making a single request is the same as th | "An HTTP method is idempotent if the intended effect on the server of making a single request is the same as the effect of making several identical req" | 11-167 |
| [2] | Idempotency is one of the most important concepts when designing reliable HTTP APIs. | "Idempotency is one of the most important concepts when designing reliable HTTP APIs. It describes what happens when the same request is performed more" | 165-350 |

---
*3 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*