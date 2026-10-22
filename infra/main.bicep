// Infrastructure as code for the existing Inside the Game deployment (documentation of what runs today).
// Deploying this template is NOT part of the hackathon demo: the resources already exist in rg-insidethegame.
// Usage (new environment):  az deployment group create -g <rg> -f infra/main.bicep -p infra/main.parameters.json
targetScope = 'resourceGroup'

@description('Short suffix that keeps global names unique')
param suffix string = 'alv'
param location string = resourceGroup().location
@description('Container image, e.g. acrinsidethegamealv.azurecr.io/insidethegame:v11')
param image string
@description('Model deployment name (cheapest capable model)')
param modelName string = 'gpt-4.1-mini'
@description('Model capacity in thousands of tokens per minute')
param modelCapacity int = 100
@description('App-side TPM guard; keeps calls under the deployment quota')
param appTpmLimit string = '30000'

var name = 'insidethegame'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${name}'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${name}${suffix}'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// Azure AI Services (Foundry resource): Azure OpenAI + Content Safety on one endpoint
resource ai 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: 'ais-${name}-${suffix}'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'ais-${name}-${suffix}'
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: ai
  name: name
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {}
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: ai
  name: modelName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: { model: { format: 'OpenAI', name: modelName, version: '2025-04-14' } }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${name}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${name}'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      registries: [ { server: acr.properties.loginServer, identity: 'system' } ]
      secrets: [ { name: 'aoai-key', value: ai.listKeys().key1 } ]
    }
    template: {
      containers: [
        {
          name: 'app'
          image: image
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'ITG_LLM_PROVIDER', value: 'azure' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: ai.properties.endpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: modelName }
            { name: 'AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'aoai-key' }
            { name: 'ITG_BATCH_S', value: '300' }
            { name: 'ITG_CONTENT_SAFETY', value: '0' }
            { name: 'ITG_TPM_LIMIT', value: appTpmLimit }
          ]
          probes: [
            { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 10 }
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30 }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

// Pull images with the app's managed identity (AcrPull)
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, app.id, 'acrpull')
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

output url string = 'https://${app.properties.configuration.ingress.fqdn}'
output foundryProjectEndpoint string = 'https://${ai.name}.services.ai.azure.com/api/projects/${project.name}'
