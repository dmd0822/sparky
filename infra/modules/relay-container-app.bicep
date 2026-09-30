targetScope = 'resourceGroup'

@description('Relay Container App name.')
param appName string

@description('Azure region for the relay app.')
param location string = resourceGroup().location

@description('Tags applied to all resources.')
param tags object

@description('Container Apps managed environment resource ID.')
param managedEnvironmentId string

@description('Container image for the relay shell. Code CD overrides this with the built relay image.')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Container port exposed by the relay image.')
param targetPort int = 80

@description('Container CPU allocation.')
param cpu string = '0.25'

@description('Container memory allocation.')
param memory string = '0.5Gi'

@description('Minimum active replicas.')
@minValue(0)
param minReplicas int = 0

@description('Maximum active replicas.')
@minValue(1)
param maxReplicas int = 1

@description('Optional ACR login server. When set, the app uses its system identity for future private image pulls.')
param acrLoginServer string = ''

@description('Optional relay app registration identifier URI, for example api://<relay-app-id>. Supplied at deploy time because Entra app registrations are Microsoft Graph objects that Bicep does not manage.')
param relayAudience string = ''

@description('Microsoft Entra tenant ID accepted by the relay.')
param azureTenantId string

@description('Optional Pi-to-relay device-code scope. Defaults to <relayAudience>/.default when relayAudience is set.')
param relayDeviceScope string = ''

@description('Managed-identity scope used by the relay when calling Foundry.')
param foundryScope string = 'https://cognitiveservices.azure.com/.default'

@description('Managed-identity scope used by the relay when calling Speech.')
param speechScope string = 'https://cognitiveservices.azure.com/.default'

var effectiveRelayDeviceScope = empty(relayDeviceScope) && !empty(relayAudience) ? '${relayAudience}/.default' : relayDeviceScope
var relayEnv = [
  {
    name: 'AZURE_TENANT_ID'
    value: azureTenantId
  }
  {
    name: 'SPARKY_RELAY_AUDIENCE'
    value: relayAudience
  }
  {
    name: 'SPARKY_RELAY_DEVICE_SCOPE'
    value: effectiveRelayDeviceScope
  }
  {
    name: 'SPARKY_FOUNDRY_SCOPE'
    value: foundryScope
  }
  {
    name: 'SPARKY_SPEECH_SCOPE'
    value: speechScope
  }
]

resource relay 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: empty(acrLoginServer) ? [] : [
        // Baseline image is public. Future private ACR images need pre-granted AcrPull or a two-phase identity/RBAC deployment to avoid first-pull RBAC propagation races.
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'relay'
          image: image
          // The relay validates that inbound device tokens carry this audience.
          // Empty on the baseline public image, which serves no relay routes.
          env: empty(relayAudience) ? [] : relayEnv
          resources: {
            cpu: json(cpu)
            memory: memory
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

output appName string = relay.name
output appResourceId string = relay.id
output principalId string = relay.identity.principalId
output ingressFqdn string = relay.properties.configuration.ingress.fqdn
