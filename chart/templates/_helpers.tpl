{{/*
Expand the name of the chart.
*/}}
{{- define "injecto.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "injecto.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "injecto.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "injecto.labels" -}}
helm.sh/chart: {{ include "injecto.chart" . }}
{{ include "injecto.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "injecto.selectorLabels" -}}
app.kubernetes.io/name: {{ include "injecto.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "injecto.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "injecto.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the proper image name
*/}}
{{- define "injecto.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end }}

{{/*
Return the command to run Injecto in API mode
*/}}
{{- define "injecto.command" -}}
- python
- ./src/main.py
- --api
{{- if .Values.injecto.api.host }}
- --host
- {{ .Values.injecto.api.host }}
{{- end }}
{{- if .Values.injecto.api.port }}
- --port
- {{ .Values.injecto.api.port | quote }}
{{- end }}
{{- if .Values.injecto.api.debug }}
- --debug
{{- end }}
{{- range .Values.injecto.extraArgs }}
- {{ . }}
{{- end }}
{{- end }}
