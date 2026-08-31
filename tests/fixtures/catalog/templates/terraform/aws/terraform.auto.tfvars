# -------------------------------------------------------------------
# GLOBAL
# -------------------------------------------------------------------

# @param region
region = "eu-west-1"
# @param globalPrefix
global_prefix = "my-project"
# @param name
environment = "development"

# -------------------------------------------------------------------
# VPC -- exercises convention A (az_count) and B (vpc_cidr), plus one
# genuinely renamed leaf carried by catalog/legacy-paths.txt.
# -------------------------------------------------------------------

# @module services.vpc | displayName=Network
# @param services.vpc.cidr
vpc_cidr = "10.0.0.0/16"
# @param services.vpc.azCount
az_count = 2
# @param services.vpc.createPublicSubnets
create_public_subnets = true
# @param services.vpc.natGateway
nat_gateway_strategy = "SINGLE"
# @param services.vpc.publicSubnetTags
public_subnet_tags = {}

# -------------------------------------------------------------------
# RDS -- convention B throughout, and the declared-type escape hatch
# for a literal that cannot be inferred.
# -------------------------------------------------------------------

# @module services.rds | displayName=Relational database
# @param services.rds.engine
rds_engine = "postgres"
# @param services.rds.engineVersion
rds_engine_version = "15"
# @param services.rds.instanceClass | type=dropdown | options=["db.t3.micro", "db.t3.small"]
rds_instance_class = "db.t3.micro"
# @param services.rds.allocatedStorage
rds_allocated_storage = 20
# @param services.rds.multiAz
rds_multi_az = true
# @param services.rds.parameters | valueType=list
rds_parameters = []
