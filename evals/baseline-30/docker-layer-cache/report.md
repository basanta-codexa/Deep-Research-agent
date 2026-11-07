# Docker Build Layer Cache Invalidation: Key Triggers and Edge Cases

## Summary
COPY . . instructions invalidate the cache by changing every build. [1]  
At least one source reports that changing build args or env variables between runs causes cache misses on ARG or ENV instructions. [1]  

## Dockerfile Instructions that Trigger Cache Invalidation
The most common culprit is a `COPY . .` early in the Dockerfile that changes every build, forcing every later step to re‑execute. [1]  
When a Dockerfile contains `ARG` or `ENV` instructions, inconsistent values between builds cause cache misses on those specific layers. [1]  

## Effect of Base Image Changes
Every layer after `FROM` is chained to the base image, so a new base digest invalidates all of them. [2]  
Pinning the base image digest freezes it until the digest changes, so updates only occur on a scheduled rebuild. [2]  

## Build Context and Build Arguments
No evidence is available regarding the effect of changing the build context on cache validity.  
Build arguments and environment variables influence cache invalidation only when their values differ between runs, as noted above. [1]  

## Limitations
- No evidence is available regarding the impact of altering the build context on cache validity.

## References

1. Fix Docker Build Cache Invalidation Slow Builds | Buglyst — https://buglyst.com/learn/guides/docker-layer-cache-invalidation-debug
2. Why Does a Base Image Update Invalidate My Cache? | WarpBuild — https://www.warpbuild.com/answers/why-do-my-docker-builds-lose-cache-after-a-base-image-update

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | COPY . . instructions invalidate the cache by changing every build | "The most common culprit is a COPY . . early in the Dockerfile that changes every build, forcing every later step to re-execute." | 605-732 |
| [1] | Changing build args or env variables between runs causes cache misses on ARG or ENV instructions. | "Another cause is inconsistent build context or build args that differ between runs, causing cache misses on ARG or ENV instructions." | 733-865 |
| [2] | Pinning the base image digest freezes it until the digest changes, so updates only occur on a scheduled rebuil | "Pinning freezes the base image until a commit changes the digest, so the update arrives on the scheduled bump rather than on the next build." | 1057-1197 |
| [2] | Updating the base image invalidates all downstream layers, causing the Dockerfile to rebuild from scratch. | "Every layer after FROM is chained to the base image, so a new base digest invalidates all of them." | 50-148 |

---
*4 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*