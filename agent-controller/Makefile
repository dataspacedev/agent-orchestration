IMG ?= agent-controller:latest
GOBIN ?= $(shell go env GOPATH)/bin
CONTROLLER_GEN = $(GOBIN)/controller-gen

.PHONY: all
all: build

## setup: download dependencies and generate go.sum
.PHONY: setup
setup:
	go mod tidy

## generate: regenerate DeepCopy methods (requires controller-gen)
.PHONY: generate
generate: controller-gen
	$(CONTROLLER_GEN) object:headerFile="hack/boilerplate.go.txt" paths="./..."

## manifests: regenerate CRD and RBAC manifests from kubebuilder markers
.PHONY: manifests
manifests: controller-gen
	$(CONTROLLER_GEN) rbac:roleName=agent-controller-role crd paths="./..." \
		output:crd:artifacts:config=config/crd/bases \
		output:rbac:artifacts:config=config/rbac

## fmt: run go fmt
.PHONY: fmt
fmt:
	go fmt ./...

## vet: run go vet
.PHONY: vet
vet:
	go vet ./...

## test: run unit tests
.PHONY: test
test: fmt vet
	go test ./... -v -count=1

## build: build the manager binary
.PHONY: build
build: fmt vet
	go build -o bin/manager ./cmd/main.go

## run: run the controller locally against the current kubeconfig context
.PHONY: run
run: fmt vet
	go run ./cmd/main.go

## docker-build: build the container image
.PHONY: docker-build
docker-build:
	docker build --platform linux/arm64 -t $(IMG) .

## docker-push: push the container image
.PHONY: docker-push
docker-push:
	docker push $(IMG)

## install: apply CRDs to the current cluster
.PHONY: install
install: manifests
	kubectl apply -f config/crd/bases/

## uninstall: remove CRDs from the current cluster
.PHONY: uninstall
uninstall:
	kubectl delete -f config/crd/bases/ --ignore-not-found

## deploy: build image and deploy controller + RBAC to the current cluster
.PHONY: deploy
deploy: manifests docker-build
	kubectl apply -f config/rbac/namespace.yaml
	kubectl apply -f config/rbac/
	kubectl apply -f config/manager/

## undeploy: remove controller and RBAC from the current cluster
.PHONY: undeploy
undeploy:
	kubectl delete -f config/manager/ --ignore-not-found
	kubectl delete -f config/rbac/ --ignore-not-found

.PHONY: controller-gen
controller-gen:
	@[ -f $(CONTROLLER_GEN) ] || GOBIN=$(GOBIN) go install sigs.k8s.io/controller-tools/cmd/controller-gen@v0.20.1
