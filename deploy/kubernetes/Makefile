# The Kubernetes packaging's tasks: the two images, the chart's checks, and the kind cluster that TESTING.md walks
# through. Run them from this directory (deploy/kubernetes/); `make` lists them.
TAG ?= $(shell git rev-parse --short HEAD)
REGISTRY ?=
DOMAIN ?= examleaf.in
# compiled into the frontend's build (examleaf-frontend/Dockerfile): change one, build again; empty: off
RAZORPAY_KEY_ID ?=
TURNSTILE_SITE_KEY ?=
PUBLIC_MEDIA_DOMAIN ?=
CLUSTER ?= examleaf-test
NAMESPACE ?= examleaf
RELEASE ?= examleaf
CHART := examleaf-platform
WEB_IMAGE := $(REGISTRY)examleaf-web:$(TAG)
FRONTEND_IMAGE := $(REGISTRY)examleaf-frontend:$(TAG)

# What a cluster needs before the chart (README.md, "Operators first"), each at a pinned release
INGRESS_NGINX := https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/kind/deploy.yaml
CERT_MANAGER := https://github.com/cert-manager/cert-manager/releases/download/v1.21.2/cert-manager.yaml
CNPG := https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.30/releases/cnpg-1.30.1.yaml
BARMAN_PLUGIN := https://github.com/cloudnative-pg/plugin-barman-cloud/releases/download/v0.15.1/manifest.yaml
# ingress-nginx's own settings that keep Caddy's behaviour (README.md, "The ingress controller")
INGRESS_NGINX_CONFIG := {"data":{"hsts":"false","use-gzip":"true","client-header-timeout":"10"}}

.DEFAULT_GOAL := help
.PHONY: help images push deps lint kind-up kind-secrets kind-load kind-install kind-down

help: ## list the tasks
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/'

images: ## build examleaf-web and examleaf-frontend tagged TAG (the git commit), the frontend for https://DOMAIN
	docker build --tag $(WEB_IMAGE) ../../examleaf-web
	docker build --tag $(FRONTEND_IMAGE) \
	  --build-arg NEXT_PUBLIC_SITE_URL=https://$(DOMAIN) \
	  --build-arg NEXT_PUBLIC_RAZORPAY_KEY_ID=$(RAZORPAY_KEY_ID) \
	  --build-arg NEXT_PUBLIC_TURNSTILE_SITE_KEY=$(TURNSTILE_SITE_KEY) \
	  --build-arg NEXT_PUBLIC_MEDIA_HOST=$(PUBLIC_MEDIA_DOMAIN) \
	  --build-arg NEXT_PUBLIC_RELEASE=$(TAG) \
	  ../../examleaf-frontend

push: ## push both images to REGISTRY (with its trailing slash: REGISTRY=ghcr.io/lazyindianbook/)
	docker push $(WEB_IMAGE)
	docker push $(FRONTEND_IMAGE)

deps: ## fetch the chart's dependencies (the erpnext chart, switched off) into examleaf-platform/charts/
	helm dependency build $(CHART)

lint: deps ## helm lint and helm template, with the default values and with values-kind.yaml
	helm lint $(CHART)
	helm lint $(CHART) -f $(CHART)/values-kind.yaml
	helm template $(RELEASE) $(CHART) > /dev/null
	helm template $(RELEASE) $(CHART) -f $(CHART)/values-kind.yaml > /dev/null

kind-up: ## the kind cluster with ingress-nginx, cert-manager, CloudNativePG, its Barman Cloud plugin and kind-extras.yaml
	kind create cluster --name $(CLUSTER) --config kind-config.yaml
	kubectl apply -f $(INGRESS_NGINX)
	kubectl -n ingress-nginx patch configmap ingress-nginx-controller --type merge -p '$(INGRESS_NGINX_CONFIG)'
	kubectl apply -f $(CERT_MANAGER)
	kubectl apply --server-side -f $(CNPG)
	kubectl -n cert-manager rollout status deployment/cert-manager-webhook --timeout 300s
	kubectl apply -f $(BARMAN_PLUGIN)
	kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout 300s
	kubectl -n cnpg-system rollout status deployment/cnpg-controller-manager --timeout 300s
	kubectl -n cnpg-system rollout status deployment/barman-cloud --timeout 300s
	kubectl apply -f kind-extras.yaml

kind-secrets: ## the test cluster's Secrets, each made once with fresh random values (never written to a file)
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n $(NAMESPACE) get secret $(RELEASE)-env > /dev/null 2>&1 || kubectl -n $(NAMESPACE) create secret generic $(RELEASE)-env \
	  --from-literal=SECRET_KEY=$$(openssl rand -hex 32) \
	  --from-literal=LEARN_CODE_SECRET=$$(openssl rand -hex 32) \
	  --from-literal=INTERNAL_API_TOKEN=$$(openssl rand -hex 24)
	kubectl -n $(NAMESPACE) get secret $(RELEASE)-health-auth > /dev/null 2>&1 || kubectl -n $(NAMESPACE) create secret generic $(RELEASE)-health-auth \
	  --from-literal=auth="monitor:{PLAIN}$$(openssl rand -hex 24)"
	kubectl -n $(NAMESPACE) get secret $(RELEASE)-backup > /dev/null 2>&1 || { KEY=$$(openssl rand -hex 10) SECRET=$$(openssl rand -hex 20) \
	  && kubectl -n s3 create secret generic rustfs-root --from-literal=RUSTFS_ACCESS_KEY=$$KEY --from-literal=RUSTFS_SECRET_KEY=$$SECRET \
	  && kubectl -n $(NAMESPACE) create secret generic $(RELEASE)-backup \
	       --from-literal=AWS_ACCESS_KEY_ID=$$KEY --from-literal=AWS_SECRET_ACCESS_KEY=$$SECRET; }

kind-load: ## copy the two images into the kind node (no registry)
	kind load docker-image $(WEB_IMAGE) $(FRONTEND_IMAGE) --name $(CLUSTER)

kind-install: deps ## helm install (or upgrade) the release into kind with values-kind.yaml
	helm upgrade --install $(RELEASE) $(CHART) --namespace $(NAMESPACE) --create-namespace \
	  -f $(CHART)/values-kind.yaml --set image.tag=$(TAG) --set frontend.image.tag=$(TAG) --set admin.image.tag=$(TAG) \
	  --wait --timeout 15m

kind-down: ## delete the kind cluster, then the dangling images
	kind delete cluster --name $(CLUSTER)
	docker image prune -f
