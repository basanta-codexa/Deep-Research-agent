# Multi‑Stage Docker Builds: Shrinking Image Footprint

## Summary
A multi‑stage Docker build allows a Dockerfile to define multiple `FROM` instructions, each creating a separate build context. [1]  
Unlike a single‑stage build, the final image is assembled from the last stage, excluding the intermediate stages that contain build tools. [1, 2]  
This separation removes compilers, development dependencies, and intermediate artifacts from the runtime image, reducing its size. [1, 2]  
Typical reductions range from 50 % to 95 %, with Node.js projects shrinking from 1.2 GB to 100–200 MB. [3]

## Definition and Mechanics
A multi‑stage Dockerfile contains multiple `FROM` directives, each starting a new stage that can use a different base image. [1]  
The last stage is the one that is exported as the final image; earlier stages are discarded after the build. [1]

## Separation of Dependencies
Build‑time dependencies such as compilers, build tools, and source code are placed in an earlier stage. [1]  
Runtime dependencies, like the compiled binary and minimal libraries, are copied into the final stage. [1]  
Because only the runtime files are copied, the final image contains nothing else. [2]  
Caching of the dependency layer means that when source code changes only the application layer is rebuilt, keeping the image size stable. [2]

## Concrete Example and Size Impact
A typical React application using Create React App can be built with the following multi‑stage Dockerfile: [4]  

```dockerfile
# Stage 1 – build
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2 – production
FROM nginx:1.23-alpine
COPY --from=builder /app/build /usr/share/nginx/html
```

In a single‑stage build that includes `node_modules` and the build tools, the image might reach 1.2 GB, whereas the multi‑stage version typically ends up around 100–200 MB. [3]

## Best Practices
Use a minimal base image for the final stage, such as Alpine or distroless, to avoid unnecessary libraries. [5]  
Remove build artifacts and temporary files before copying to the final stage. [5]  
Leverage Docker’s layer caching by ordering commands so that unchanged layers are reused. [2]  
Keep the final stage as small as possible by only copying the files required for execution. [2]

## Limitations
- The evidence does not provide detailed command syntax for cleaning caches or specifying minimal base images beyond general guidance. [5]  
- Size‑reduction percentages are derived from a Node.js example; other languages or frameworks may experience different savings. [3]

## References

1. DevToolsHub — Free Developer Tools — https://devtoolshub.net/blog/multi-stage-docker-builds
2. Docker Multi-Stage Builds: How I Reduced Image Sizes by 94% (With Real Examples) — https://dev.to/sanjaysundarmurthy/docker-multi-stage-builds-how-i-reduced-image-sizes-by-94-with-real-examples-276d
3. Docker Multi-Stage Builds — Reduce Image Size from 1GB to 50MB — https://devopskit.in/blog/docker-multi-stage-build-guide/
4. Docker Multi-Stage Builds: 90% Image Size Reduction Guide — https://serversium.com/en/blog/docker-multi-stage-builds-complete-guide
5. Optimize Docker Images with Multi-Stage Builds: A Comprehensive Guide | Master DevOps Tools & Best Practices - DevOps Knowledge Hub — https://devops.aibit.im/en/article/optimize-docker-images-multi-stage-builds

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | One stage can contain compilers, development dependencies and build tools, while another contains only the fil | "One stage can contain compilers, development dependencies and build tools, while another contains only the files and runtime dependencies required to " | 585-764 |
| [2] | The final image contains only what your application needs to run, excluding build dependencies. | "The final image contains only what your application needs to run — nothing else." | 422-502 |
| [2] | Separating dependencies into a separate stage allows caching of the dependency layer, so that only the applica | "Docker caches the dependency layer — so when only your code changes, the rebuild copies just the application layer ( usually <1MB)." | 1203-1334 |
| [3] | Multi-stage builds typically reduce image sizes by 50–95%, e.g., a Node.js application might go from 1.2 GB to | "Multi-stage builds typically reduce image sizes by 50-95%. A Node.js application might go from 1.2GB (with node_modules and build tools) to 100-200MB " | 821-1007 |
| [4] | The source provides a complete multi-stage Dockerfile for a React application using Create React App. | "Here's a complete multi-stage Dockerfile for a React application using Create React App:" | 1296-1384 |
| [5] | Separate build dependencies from the runtime image to reduce size | "Learn how to optimize your Dockerfiles by separating build dependencies, ensuring only necessary components reach your final runtime image." | 601-740 |

---
*6 passages from 5 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*