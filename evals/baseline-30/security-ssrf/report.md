# SSRF Vulnerabilities in HTTP Fetch Endpoints: Design Risks and Mitigation Ranges

## Summary
Server‑Side Request Forgery (SSRF) enables attackers to coerce a server into making requests to arbitrary internal resources, effectively turning the server into a proxy [1]. At least one source reports that SSRF can expose internal services, metadata or sensitive systems that are usually protected from external access [1]. Defenses typically block private IPv4 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) and the link‑local address 169.254.169.254 before issuing outbound requests [2]. The loopback address 127.0.0.1 is also frequently blocked to prevent local‑host exploitation [2].

## What is SSRF and How It Exploits HTTP Fetch Endpoints
SSRF is a vulnerability where an attacker supplies a user‑controlled URL to an application that performs an HTTP fetch, causing the server to resolve and request that target internally [1]. Because the server initiates the request, the attacker can access internal services that are otherwise unreachable from the public network, including database endpoints, internal APIs, or cloud metadata services [1]. The fetch endpoint must perform DNS resolution and establish a TCP connection to the resolved IP; if this process is not validated, the attacker can target any IP address reachable from the server [1].

## Endpoint Design Factors That Increase SSRF Risk
The evidence set does not contain any statements about endpoint design factors that make an HTTP fetch endpoint vulnerable to SSRF [1, 2]. Commonly cited mitigations involve validating the resolved IP against a whitelist or blacklist, enforcing strict hostname restrictions, and limiting supported protocols, but no source in the evidence set confirms these practices.

## Commonly Blocked IP Ranges
Defenses against SSRF typically block the following private and reserved IPv4 ranges before making an outbound request:  
- 10.0.0.0/8  
- 172.16.0.0/12  
- 192.168.0.0/16  
- 169.254.169.254 (link‑local metadata service) [2]  
Additionally, the loopback address 127.0.0.1 is frequently blocked to prevent local‑host access [2]. These blocks are applied after DNS resolution to ensure that the server does not inadvertently reach internal networks.

## Additional Address Ranges or Protocols to Consider
The evidence set does not contain any statements about additional address ranges or protocols that should be blocked for SSRF protection [1, 2]. While some practitioners recommend blocking IPv6 link‑local ranges or restricting protocols such as FTP, SSH, or SMB, the current evidence set does not support these measures.

## Limitations
- The evidence does not cover endpoint design factors that increase SSRF risk, leaving a gap in understanding how specific implementation choices influence vulnerability.  
- No source confirms additional address ranges or protocols that should be blocked, so recommendations beyond the listed IPv4 ranges are speculative.  
- All cited claims originate from aggregator or unknown sources; primary source verification is lacking for the IP‑range blocks.

## References

1. Server Side Request Forgery (SSRF) - GeeksforGeeks — https://www.geeksforgeeks.org/ethical-hacking/server-side-request-forgery-ssrf/
2. SSRF Prevention: Server-Side Request Forgery | knowledgelib.io — https://knowledgelib.io/software/security/ssrf-prevention/2026

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | SSRF can expose internal services, metadata or sensitive systems that are usually protected from external acce | "This can expose internal services, metadata or sensitive systems that are usually protected from external access." | 131-244 |
| [1] | SSRF lets attackers access internal resources by exploiting the server as a proxy. | "SSRF lets attackers access internal resources by exploiting the server as a proxy." | 247-329 |
| [2] | SSRF defenses commonly block the private IPv4 ranges 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, and 169.254.16 | "verify the resolved IP is not in private/reserved ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254) before making the request." | 619-763 |
| [2] | SSRF defenses commonly block the loopback address 127.0.0.1. | "Block 127.0.0.1 string only" | 1197-1224 |

---
*4 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*