@description('Azure region for the broker app resources.')
param location string

@description('Name of the managed environment hosting the app.')
param managedEnvironmentName string

@description('Name of the broker Container App.')
param brokerAppName string

@description('Container image for the broker app.')
param brokerImage string

@description('Container port exposed by the broker app.')
param containerPort int = 8080

@description('Minimum number of broker replicas.')
param minReplicas int = 1

@description('Maximum number of broker replicas.')
param maxReplicas int = 2

@description('Log Analytics workspace name used for app diagnostics.')
param logAnalyticsWorkspaceName string

@description('Azure Container Registry login server.')
param registryLoginServer string

@description('Azure Container Registry resource name.')
param registryName string

@description('Azure OpenAI account name.')
param openAiAccountName string

@description('Azure Speech account name.')
param speechAccountName string

@description('Azure AI Content Safety account name.')
param contentSafetyAccountName string

@description('Standard tags applied to Azure resources.')
param tags object = {}

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135fe8e8'

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiAccountName
}

resource speechAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: speechAccountName
}

resource contentSafetyAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: contentSafetyAccountName
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: managedEnvironmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

resource brokerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: brokerAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: containerPort
        allowInsecure: false
        transport: 'auto'
      }
      registries: [
        {
          server: registryLoginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'broker'
          image: brokerImage
          env: [
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openAiAccount.properties.endpoint
            }
            {
              name: 'AZURE_OPENAI_MODEL'
              value: 'gpt-4o-mini'
            }
            {
              name: 'AZURE_SPEECH_ENDPOINT'
              value: speechAccount.properties.endpoint
            }
            {
              name: 'AZURE_CONTENT_SAFETY_ENDPOINT'
              value: contentSafetyAccount.properties.endpoint
            }
            {
              name: 'BROKER_PORT'
              value: string(containerPort)
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: containerPort
              }
              periodSeconds: 30
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: containerPort
              }
              periodSeconds: 15
              timeoutSeconds: 5
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, brokerApp.id, 'acr-pull')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: brokerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource openAiUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAiAccount.id, brokerApp.id, 'openai-user')
  scope: openAiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
    principalId: brokerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource speechUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speechAccount.id, brokerApp.id, 'speech-user')
  scope: speechAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: brokerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource contentSafetyUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(contentSafetyAccount.id, brokerApp.id, 'content-safety-user')
  scope: contentSafetyAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: brokerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output containerAppName string = brokerApp.name
output containerAppFqdn string = brokerApp.properties.configuration.ingress.fqdn
output managedEnvironmentName string = managedEnvironment.name
output managedIdentityPrincipalId string = brokerApp.identity.principalId
