# @label "Name"
# @group "Basic"
variable "name" {
  type        = string
  description = "name for deployed cluster"
}
# @label "Public Endpoint"
# @group "Basic"
variable "public_endpoint" {
  type        = bool
  default     = true
  description = "expose node port access for the LLM service UI"
}
# @label "Min Replica"
# @group "Basic"
variable "min_replica" {
  type        = number
  default     = 1
  description = "min replica for the LLM service, automatically scale the number of replicas for your LLM service within min and max based on the load"
}
# @label "Max Replica"
# @group "Basic"
variable "max_replica" {
  type        = number
  default     = 1
  description = "max replica for the LLM service, automatically scale the number of replicas for your LLM service within min and max based on the load"
}