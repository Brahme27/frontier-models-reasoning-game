# NAT-free VPC with two tiers in two AZs:
#   * public subnets  - Fargate tasks (public IP for egress to Bedrock / OpenAI APIs; their
#                       security group only accepts traffic from the ALB)
#   * private subnets - the internal ALB, reachable only through a CloudFront VPC origin
# No NAT gateway = ~$32/month saved.

variable "name" { type = string }
variable "cidr" {
  type    = string
  default = "10.20.0.0/16"
}

# A few AZs do not support CloudFront VPC origins; never place the ALB there.
data "aws_availability_zones" "available" {
  state            = "available"
  exclude_zone_ids = ["use1-az3", "usw1-az2", "apne1-az3", "cac1-az3"]
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

# Also required for CloudFront VPC origins ("denotes that the VPC can receive internet traffic").
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = var.name }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${var.name}-private-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${var.name}-public" }
}

# Local routes only: nothing in these subnets is reachable from (or can reach) the internet.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name}-private" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

output "vpc_id" { value = aws_vpc.this.id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "internet_gateway_id" { value = aws_internet_gateway.this.id }
