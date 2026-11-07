# ETag and If‑None‑Match: Efficient Conditional GETs

## Summary
The **ETag** header is a server‑generated identifier that represents a specific version of a resource. Clients store this value and send it back in an **If‑None‑Match** request header to ask the server whether the cached representation is still current. If the ETag matches the current resource, the server replies with **304 Not Modified** and omits the body, allowing the client to reuse its cached copy. The 304 response must include select headers from the original 200 response to maintain cache validity. This mechanism reduces bandwidth and latency for repeated requests. [1, 2, 3, 4]

## Purpose of the ETag Header
The ETag header is sent by the server to uniquely identify the current state of a resource. It allows the client to later determine whether the resource has changed. [1]

## Client Use of the ETag Value
After receiving an ETag, the client stores it with the cached representation. On subsequent requests for the same resource, the client includes the stored ETag in an **If‑None‑Match** header. This tells the server to compare the supplied tag with the current version. [1]

## Server Response When the ETag Matches
When the ETag supplied by the client matches the current resource, the server returns **304 Not Modified**. The response contains no message body and indicates that the cached representation is still valid. [1]

## Interpreting a 304 Not Modified
Upon receiving a 304, the client understands that the entity tag failed the condition and that the cached representation can be reused. The response carries no body, so the client skips downloading any data. [2]

## Required Headers in a 304 Response
A 304 response must include a subset of headers that would have been sent with a 200 response, specifically **Cache‑Control, Content‑Location, Date, ETag, Expires,** and **Vary**. These headers ensure that the cached entry remains valid and that any caching directives are respected. [3, 4]

## Limitations
- The evidence does not detail how the ETag is generated or the exact semantics of weak versus strong validators.
- No source explains the interaction between other caching headers (e.g., `Last-Modified`) and ETag usage.
- The role of `If-Modified-Since` is not covered by the provided evidence.

## References

1. 304 Not Modified — https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304
2. 304 Not Modified — https://http.dev/304
3. If-None-Match — https://http.dev/if-none-match
4. If-None-Match header — https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-None-Match

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | The server sends a 304 Not Modified response when the ETag matches the current resource. | "Because the etag value matches at the time of the request, the entity tag fails the condition, and a 304 response is returned:" | 878-1004 |
| [2] | The client reuses its cached representation and does not download the response body when receiving a 304 Not M | "The response carries no message body and instructs the client to reuse its stored representation." | 162-259 |
| [3] | When a 304 Not Modified is returned, the response must include Cache‑Control, Content‑Location, Date, ETag, Ex | "When the server returns 304, the response includes headers from the original successful response: Cache-Control, Content-Location, Date, ETag, Expires" | 616-777 |
| [4] | When the condition fails for GET and HEAD methods, the server must return a 304 Not Modified and any of the fo | "When the condition fails for GET and HEAD methods, the server must return a 304 Not Modified and any of the following header fields that would have be" | 351-611 |

---
*4 passages from 4 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*