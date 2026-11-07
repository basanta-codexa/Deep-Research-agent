# Handling HTTP 429 Responses with Retry-After

## Summary
The Retry-After header, when present, specifies the time a client should wait before retrying [1]. Clients should honor the header exactly, avoiding immediate retries [2].

## Parsing the Retry-After Header
The Retry-After header accepts two formats. A non‑negative decimal integer indicates the number of seconds to delay after the response is received [1]. Alternatively, an HTTP-date specifies an absolute point in time after which the client may retry, using the standard HTTP date format [1].

## Recommended Client Behavior
When a 429 response includes a Retry-After header, the client should wait exactly the duration specified before issuing another request [2]. Ignoring the header and retrying immediately is discouraged, as it can exacerbate server load [2].

## Limitations
- The provided evidence does not describe the official semantics of status code 429 itself.  
- No source discusses exponential backoff, jitter, or other adaptive retry strategies after a 429 response.  
- Guidance for missing, malformed, or past Retry-After headers is absent from the available records.

## References

1. Retry-After header — https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After
2. API Rate Limit 429 Debugging Guide | Buglyst — https://buglyst.com/learn/guides/api-rate-limit-429-debug

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | The header value can be a non-negative decimal integer indicating the seconds to delay after the response is r | "A non-negative decimal integer indicating the seconds to delay after the response is received." | 807-901 |
| [1] | The header value can be an HTTP-date. | "A date after which to retry. See the Date header for more details on the HTTP date format." | 696-786 |
| [2] | Clients should not ignore the Retry-After header and retry immediately. | "warningIgnoring Retry-After header and retrying immediately" | 665-724 |
| [2] | Clients should wait exactly the duration specified in the Retry-After header before retrying. | "buildRead `Retry-After` header (HTTP-date or seconds) and wait exactly that duration" | 578-662 |

---
*4 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*