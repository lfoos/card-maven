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

{{/* eBay keys: only the market worker gets them. Optional; without them the
     eBay source is skipped. */}}
{{- define "card-maven.ebayEnv" -}}
- name: CARD_MAVEN_EBAY_CLIENT_ID
  valueFrom:
    secretKeyRef: { name: {{ .Values.secrets.existingSecret }}, key: ebay-client-id, optional: true }
- name: CARD_MAVEN_EBAY_CLIENT_SECRET
  valueFrom:
    secretKeyRef: { name: {{ .Values.secrets.existingSecret }}, key: ebay-client-secret, optional: true }
{{- end -}}

{{/* A CronJob. `command` is a shell line run in the workers image; or set
     `image` (a key under .Values.image) and `args` to use that image's
     entrypoint. `writableTmp` mounts an emptyDir at /tmp (the root
     filesystem is read-only). */}}
{{- define "card-maven.cronjob" -}}
{{- $root := index . 0 -}}{{- $name := index . 1 -}}{{- $job := index . 2 -}}
{{- $image := index $root.Values.image ($job.image | default "workers") -}}
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ include "card-maven.fullname" $root }}-{{ $name }}
  labels: {{- include "card-maven.labels" $root | nindent 4 }}
    app.kubernetes.io/component: {{ $name }}
spec:
  schedule: {{ $job.schedule | quote }}
  timeZone: {{ $root.Values.cronJobs.timeZone | quote }}
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: {{ $job.activeDeadlineSeconds | default 1800 }}
      template:
        metadata:
          labels: {{- include "card-maven.labels" $root | nindent 12 }}
            app.kubernetes.io/component: {{ $name }}
        spec:
          restartPolicy: Never
          serviceAccountName: {{ include "card-maven.serviceAccountName" $root }}
          containers:
            - name: {{ $name }}
              image: {{ include "card-maven.image" (list $root $image) }}
              imagePullPolicy: {{ $root.Values.image.pullPolicy }}
              {{- if $job.command }}
              command: ["sh", "-c", {{ $job.command | quote }}]
              {{- else }}
              args: {{- toJson $job.args | nindent 16 }}
              {{- end }}
              {{- include "card-maven.env" $root | nindent 14 }}
              {{- include "card-maven.containerSecurity" $root | nindent 14 }}
              resources: {{- toYaml ($job.resources | default $root.Values.cronJobs.resources) | nindent 16 }}
              {{- if $job.writableTmp }}
              volumeMounts:
                - { name: tmp, mountPath: /tmp }
              {{- end }}
          {{- if $job.writableTmp }}
          volumes:
            - { name: tmp, emptyDir: { sizeLimit: 256Mi } }
          {{- end }}
{{- end -}}
