# Build stage
FROM golang:1.22-alpine AS builder

WORKDIR /workspace

# Cache module downloads as a separate layer
COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-s -w" \
    -o manager \
    ./cmd/main.go

# Runtime stage — distroless/static for minimal attack surface; runs as nonroot (uid 65532)
FROM gcr.io/distroless/static:nonroot

WORKDIR /

COPY --from=builder /workspace/manager .

USER 65532:65532

ENTRYPOINT ["/manager"]
