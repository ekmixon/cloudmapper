import pyjq

from shared.common import query_aws, get_regions, get_parameter_file
from shared.nodes import Account, Region
from commands.prepare import get_resource_nodes


def find_unused_security_groups(region):
    defined_sgs = query_aws(region.account, "ec2-describe-security-groups", region)

    network_interfaces = query_aws(
        region.account, "ec2-describe-network-interfaces", region
    )

    defined_sg_set = {
        sg["GroupId"]: sg for sg in pyjq.all(".SecurityGroups[]?", defined_sgs)
    }


    used_sgs = set(
        pyjq.all(".NetworkInterfaces[]?.Groups[].GroupId", network_interfaces)
    )

    # Get the data from the `prepare` command
    outputfilter = {
        "internal_edges": True,
        "read_replicas": True,
        "inter_rds_edges": True,
        "azs": False,
        "collapse_by_tag": None,
        "collapse_asgs": True,
        "mute": True,
    }
    nodes = get_resource_nodes(region, outputfilter)

    for _, node in nodes.items():
        used_sgs.update(node.security_groups)

    unused_sg_ids = set(defined_sg_set) - used_sgs
    return [
        {
            "id": sg_id,
            "name": defined_sg_set[sg_id]["GroupName"],
            "description": defined_sg_set[sg_id].get("Description", ""),
        }
        for sg_id in unused_sg_ids
    ]


def find_unused_volumes(region):
    volumes = query_aws(region.account, "ec2-describe-volumes", region)
    return [
        {"id": volume["VolumeId"]}
        for volume in pyjq.all(
            '.Volumes[]?|select(.State=="available")', volumes
        )
    ]


def find_unused_elastic_ips(region):
    ips = query_aws(region.account, "ec2-describe-addresses", region)
    return [
        {"id": ip.get("AllocationId", "Un-allocated IP"), "ip": ip["PublicIp"]}
        for ip in pyjq.all(
            ".Addresses[]? | select(.AssociationId == null)", ips
        )
    ]


def find_unused_network_interfaces(region):
    network_interfaces = query_aws(
        region.account, "ec2-describe-network-interfaces", region
    )
    return [
        {"id": network_interface["NetworkInterfaceId"]}
        for network_interface in pyjq.all(
            '.NetworkInterfaces[]?|select(.Status=="available")',
            network_interfaces,
        )
    ]


def find_unused_elastic_load_balancers(region):
    elastic_load_balancers = query_aws(
        region.account, "elb-describe-load-balancers", region
    )
    unused_elastic_load_balancers = [
        {
            "LoadBalancerName": elastic_load_balancer["LoadBalancerName"],
            "Type": "classic",
        }
        for elastic_load_balancer in pyjq.all(
            ".LoadBalancerDescriptions[]? | select(.Instances == [])",
            elastic_load_balancers,
        )
    ]

    elastic_load_balancers_v2 = query_aws(
        region.account, "elbv2-describe-load-balancers", region
    )
    for elastic_load_balancer in pyjq.all(
        ".LoadBalancers[]?", elastic_load_balancers_v2
    ):
        target_groups = get_parameter_file(
            region,
            "elbv2",
            "describe-target-groups",
            elastic_load_balancer["LoadBalancerArn"],
        )
        unused_elastic_load_balancers.append(
            {
                "LoadBalancerName": elastic_load_balancer["LoadBalancerName"],
                "Type": elastic_load_balancer["Type"],
            }
        )
        for target_group in pyjq.all(".TargetGroups[]?", target_groups):
            target_healths = get_parameter_file(
                region,
                "elbv2",
                "describe-target-health",
                target_group["TargetGroupArn"],
            )
            instances = pyjq.one(".TargetHealthDescriptions? | length", target_healths)
            if instances > 0:
                unused_elastic_load_balancers.pop()
                break

    return unused_elastic_load_balancers


def add_if_exists(dictionary, key, value):
    if value:
        dictionary[key] = value


def find_unused_resources(accounts):
    unused_resources = []
    for account in accounts:
        unused_resources_for_account = []
        for region_json in get_regions(Account(None, account)):
            region = Region(Account(None, account), region_json)

            unused_resources_for_region = {}

            add_if_exists(
                unused_resources_for_region,
                "security_groups",
                find_unused_security_groups(region),
            )
            add_if_exists(
                unused_resources_for_region, "volumes", find_unused_volumes(region)
            )
            add_if_exists(
                unused_resources_for_region,
                "elastic_ips",
                find_unused_elastic_ips(region),
            )
            add_if_exists(
                unused_resources_for_region,
                "network_interfaces",
                find_unused_network_interfaces(region),
            )
            add_if_exists(
                unused_resources_for_region,
                "elastic_load_balancers",
                find_unused_elastic_load_balancers(region),
            )

            unused_resources_for_account.append(
                {
                    "region": region_json["RegionName"],
                    "unused_resources": unused_resources_for_region,
                }
            )
        unused_resources.append(
            {
                "account": {"id": account["id"], "name": account["name"]},
                "regions": unused_resources_for_account,
            }
        )
    return unused_resources
