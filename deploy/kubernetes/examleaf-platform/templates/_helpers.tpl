{{/* Every resource is <fullname>-<part>: examleaf-web, examleaf-db … (fullnameOverride, else the release's name). */}}
{{- define "examleaf.fullname" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{/* The recommended labels (kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/).
     Call with (dict "ctx" $ "component" "web" "app" "examleaf-web"). */}}
{{- define "examleaf.labels" -}}
{{ include "examleaf.selectorLabels" . }}
app.kubernetes.io/version: {{ .version | default .ctx.Chart.AppVersion | quote }}
app.kubernetes.io/part-of: examleaf
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .ctx.Chart.Name .ctx.Chart.Version }}
{{- end -}}

{{- define "examleaf.selectorLabels" -}}
app.kubernetes.io/name: {{ .app | default "examleaf-web" }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* image references: "repository:tag", the tag falling back to the chart's appVersion */}}
{{- define "examleaf.image" -}}
{{- printf "%s:%s" .repository (.tag | default $.appVersion) -}}
{{- end -}}
{{- define "examleaf.webImage" -}}
{{- include "examleaf.image" (dict "repository" .Values.image.repository "tag" .Values.image.tag "appVersion" .Chart.AppVersion) -}}
{{- end -}}

{{- define "examleaf.dbCluster" -}}
{{- .Values.postgres.name | default (printf "%s-db" (include "examleaf.fullname" .)) -}}
{{- end -}}
{{- define "examleaf.envSecret" -}}
{{- .Values.secrets.env | default (printf "%s-env" (include "examleaf.fullname" .)) -}}
{{- end -}}
{{- define "examleaf.healthAuthSecret" -}}
{{- .Values.secrets.healthAuth | default (printf "%s-health-auth" (include "examleaf.fullname" .)) -}}
{{- end -}}
{{- define "examleaf.backupSecret" -}}
{{- .Values.secrets.backup | default (printf "%s-backup" (include "examleaf.fullname" .)) -}}
{{- end -}}
{{- define "examleaf.adminHost" -}}
{{- .Values.admin.host | default (printf "admin.%s" .Values.domain) -}}
{{- end -}}

{{/* The pod-level settings every pod of the site shares: no Kubernetes API token (none of them calls the API), the
     image's unprivileged user by number (runAsNonRoot cannot check a user name), the media volume writable through
     fsGroup, the runtime's default seccomp profile. */}}
{{- define "examleaf.podSpecCommon" -}}
automountServiceAccountToken: false
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
securityContext:
  {{- toYaml .Values.podSecurityContext | nindent 2 }}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/* The Django processes' environment, as docker-compose.yml's x-app gives it: the settings (ConfigMap), the secret
     settings (secrets.env, every key) and DATABASE_URL from the Secret CloudNativePG keeps for the database's owner. */}}
{{- define "examleaf.djangoEnv" -}}
envFrom:
  - configMapRef:
      name: {{ include "examleaf.fullname" . }}-config
  - secretRef:
      name: {{ include "examleaf.envSecret" . }}
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: {{ include "examleaf.dbCluster" . }}-app
        key: uri
  - name: XDG_CACHE_HOME  # fontconfig's cache for the invoice PDFs: the home directory does not exist
    value: /tmp/.cache
{{- end -}}

{{/* Worker, beat and the media worker start once web has brought the schema up to date (docker-compose.yml: they wait
     for web to be healthy). --skip-checks: the media worker's small environment has no LEARN_CODE_SECRET, whose check
     would stop the command. timeout: a connection that is never answered (a starting database) costs 30 s, not the
     two minutes of TCP's retries. */}}
{{- define "examleaf.waitForMigrations" -}}
- name: wait-for-migrations
  image: {{ include "examleaf.webImage" .ctx }}
  imagePullPolicy: {{ .ctx.Values.image.pullPolicy }}
  command:
    - sh
    - -c
    - until timeout 30 python manage.py migrate --check --skip-checks > /dev/null 2>&1; do echo "waiting for the database and its migrations"; sleep 5; done
  {{- .env | nindent 2 }}
  securityContext:
    {{- toYaml .ctx.Values.containerSecurityContext | nindent 4 }}
  resources:
    {{- toYaml .ctx.Values.initResources | nindent 4 }}
  volumeMounts:
    - {name: tmp, mountPath: /tmp}
{{- end -}}

{{/* /tmp as an emptyDir (the root filesystem is read-only) and the media volume */}}
{{- define "examleaf.djangoVolumes" -}}
- name: tmp
  emptyDir:
    sizeLimit: {{ .tmpSize }}
- name: media
  persistentVolumeClaim:
    claimName: {{ .ctx.Values.media.existingClaim | default (printf "%s-media" (include "examleaf.fullname" .ctx)) }}
{{- end -}}
{{- define "examleaf.djangoVolumeMounts" -}}
- {name: tmp, mountPath: /tmp}
- {name: media, mountPath: /app/media}
{{- end -}}
