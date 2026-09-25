targetScope = 'resourceGroup'

@description('Relay managed identity principal ID.')
param relayPrincipalId string

@description('AI Services account name for scoped Cognitive Services User assignment.')
param aiServicesAccountName string

@description('Speech account name for scoped Cognitive Services User assignment.')
param speechAccountName string

@description('ACR name for scoped AcrPull assignment.')
param acrName string

var cognitiveServicesUserRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource aiServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesAccountName
}

resource speechAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: speechAccountName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource relayAiServicesUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServicesAccount.id, relayPrincipalId, cognitiveServicesUserRoleDefinitionId)
  scope: aiServicesAccount
  properties: {
    roleDefinitionId: cognitiveServicesUserRoleDefinitionId
    principalId: relayPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource relaySpeechUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speechAccount.id, relayPrincipalId, cognitiveServicesUserRoleDefinitionId)
  scope: speechAccount
  properties: {
    roleDefinitionId: cognitiveServicesUserRoleDefinitionId
    principalId: relayPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource relayAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, relayPrincipalId, acrPullRoleDefinitionId)
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: relayPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output aiServicesRoleAssignmentId string = relayAiServicesUser.id
output speechRoleAssignmentId string = relaySpeechUser.id
output acrPullRoleAssignmentId string = relayAcrPull.id
