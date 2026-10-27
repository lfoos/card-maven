{{- define "card-maven.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "card-maven.labels" -}}
app.kubernetes.io/name: card-maven
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "card-maven.image" -}}
{{- $root := index . 0 -}}{{- $name := index . 1 -}}
{{- if $root.Values.image.registry -}}
{{- printf "%s/%s:%s" $root.Values.image.registry $name $root.Values.image.tag -}}
{{- else -}}
{{- printf "%s:%s" $name $root.Values.image.tag -}}
{{- end -}}
{{- end -}}

{{- define "card-maven.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}{{ include "card-maven.fullname" . }}{{- else -}}default{{- end -}}
{{- end -}}

{{/* Hardened defaults shared by every container. */}}
{{- define "card-maven.containerSecurity" -}}
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities: { drop: ["ALL"] }
  seccompProfile: { type: RuntimeDefault }
{{- end -}}

{{- define "card-maven.env" -}}
envFrom:
  - configMapRef:
      name: {{ include "card-maven.fullname" . }}-config
env:
  - name: CARD_MAVEN_DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: {{ .Values.secrets.existingSecret }}
        key: database-url
{{- end -}}
