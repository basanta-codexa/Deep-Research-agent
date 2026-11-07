# Understanding the HTTP Cache‑Control no‑cache Directive

## Summary
The `Cache‑Control: no‑cache` directive is defined in RFC 9111 §5.2.2.4 as requiring a cache to validate a response before reusing it, but it does not forbid storing that response [1]. A cache may store a response bearing `no‑cache`, yet it must forward the request to the origin server for validation each time the stored response is used to satisfy a subsequent request [1, 2]. In contrast, the `no‑store` directive explicitly instructs caches not to persist the response at all [2]. Therefore, `no‑cache` mandates revalidation on reuse, while `no‑store` prohibits storage entirely.

## Formal Definition of Cache‑Control: no‑cache
RFC 9111 §5.2.2.4 defines the `no‑cache` response directive as follows: “the response **MUST NOT** be used to satisfy any other request without forwarding it for validation and receiving a successful response.” Storing the response is permissible under this directive [1].

## Cache Treatment of a Response with no‑cache
A cache that receives a response containing `Cache‑Control: no‑cache` may store the response but must validate it with the origin server before serving it to any subsequent request. The cache is required to forward the request for validation and only use the stored response if the validation succeeds. The directive does not prevent the cache from storing the response in the first place [1, 2].

## Difference Between no‑cache and no‑store
`no‑cache` allows a cache to persist the response but forces revalidation on each reuse. Conversely, `no‑store` instructs caches not to store the response at all, effectively preventing any reuse from the cache. This distinction is explicitly stated in the specification and reiterated by authoritative sources: “no‑store is the directive that tells caches not to store the response” [2], while “no‑cache means a cache may store the response but must revalidate it with the origin before every reuse” [2].

## Revalidation Requirement Before Serving
The `no‑cache` directive requires a cache to revalidate the response with the origin server before it can be used to satisfy any subsequent request. This revalidation step is mandatory; a cache cannot serve a stored response without first validating it. The directive’s wording in RFC 9111 makes this requirement explicit, and the summary from howhttpworks.com confirms that revalidation is required before every reuse [1, 2].

## Limitations
- The evidence does not discuss the behavior of intermediate caches or how `no‑cache` interacts with other caching directives such as `max-age` or `must-revalidate`.  
- The sources do not provide empirical data on how widely compliant caches implement the revalidation requirement.  
- No information is available on how `no‑cache` affects conditional requests or the use of ETag/Last‑Modified headers beyond the general revalidation requirement.

## References

1. Cache-Control: no-cache does not mean "do not cache" — By... — https://bytefork.tools/blog/no-cache-does-not-mean-no-caching/
2. Cache-Control: no-cache vs no-store — https://howhttpworks.com/compare/no-cache-vs-no-store

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | The no-cache response directive requires a cache to validate the response with the origin server before using  | "RFC 9111 §5.2.2.4 defines no-cache as: the response “MUST NOT be used to satisfy any other request without forwarding it for validation and receiving " | 351-541 |
| [2] | no-store is the directive that tells caches not to store the response | "no-store is the directive that tells caches not to store the response." | 899-969 |
| [2] | no-cache does not prevent storage | "no-cache does not prevent storage." | 666-700 |
| [2] | no-cache means a cache may store the response but must revalidate it with the origin before every reuse; no-st | "TL;DR: no-cache means a cache may store the response but must revalidate it with the origin before every reuse. no-store means do not store it at all." | 0-150 |

---
*4 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*