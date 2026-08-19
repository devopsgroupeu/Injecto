# @section services.vpc begin
module "vpc" {
  cidr = var.vpc_cidr
}
# @section services.vpc end

# @section services.rds.enabled begin
module "rds" {
  engine = var.rds_engine
}
# @section services.rds.enabled end
