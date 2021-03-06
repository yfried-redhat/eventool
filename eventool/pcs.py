import collections
import json
from eventool import ssh_cmds
from eventool import logger
import xmltodict
# from lxml import etree as xml_parser
from xml.dom import minidom as xml_parser
from eventool import parsers

LOG = logger.getLogger(__name__)


@parsers.cli_command("pcs", subparser="action")
class PCSMgmt(ssh_cmds.tmp_cmd):

    def __init__(self, ssh):
        super(PCSMgmt, self).__init__(ssh)
        self._dict_xml = None
        self._cluster = None
        # self._haproxy_conf = None

    @property
    def cluster(self):
        self._cluster = self._cluster or self.status_xml()
        return self._cluster

    @parsers.cli_choice(parser="pcs", subparser="action")
    @ssh_cmds.command_decorator
    def status(self):
        """Returns full PCS status. """
        cmd = "pcs status"
        return cmd, self._noop_parser

    @ssh_cmds.command_decorator
    def status_xml(self):
        LOG.debug("Get PCS data in XML format from HA node")
        cmd = "crm_mon -X"
        return cmd, self._parse_xml

    def _parse_xml(self, raw_xml):
        self._dict_xml = xmltodict.parse(raw_xml)
        # return raw_xml
        return xml_parser.parseString(raw_xml)

    def get_resource_node(self, resource):
        [node] = resource.getElementsByTagName("node")
        return node.getAttribute("name")

    def find_service_node(self, service):
        resources = self.find_resource(service)
        if not resources:
            # TODO(yfried): replace with a better exception
            raise Exception("resource {0} NotFound".
                            format(service))
        if len(resources) > 1:
            # TODO(yfried): replace with a better exception
            raise Exception("Found multiple matches for resource {s}".
                            format(service))

        resource = resources.pop()
        return self.get_resource_node(resource)

    def get_vip_dest(self, proj):
        vip = "-".join(["ip", proj, "adm"])
        vips = self.find_resource(vip, exact_match=False)
        if not vips:
            # todo(yfried) better exception
            raise Exception("No vip found for: {proj}. Unable to find vip "
                            "named: {vip}".format(proj=proj, vip=vip))
        vip_resource = vips.pop()
        return self.get_resource_node(vip_resource)

    @staticmethod
    def strip_node_name(name):
        prefix = "pcmk-"
        assert name.startswith(prefix)
        return name[len(prefix):]

    @staticmethod
    def _find_in_tree(root, tag, id, exact=True):
        match = "__eq__" if exact else "__contains__"
        return [r for r in root.getElementsByTagName(tag)
                if getattr(r.getAttribute("id"), match)(id)]

    def find_clone(self, service):
        TAG = "clone"
        service = "%s-clone" % service
        x_list = self._find_in_tree(self.cluster, TAG, service)
        if len(x_list) > 1:
            # TODO(yfried): replace with a better exception
            raise Exception("Found multiple matches for clone {s}".
                            format(service))
        return x_list

    def get_active_resources(self, clone):
        """Returns list of active resource for :clone

        list is of len=1 if clone is A/P, if clone is A/A will return all
        resource of this clone

        :param clone:
        :return:
        """
        # get service name from clone name
        service = clone.getAttribute("id")[:-len("-clone")]
        resources = self._find_in_tree(clone, "resource", service)

        def active(resource):
            return resource.getAttribute("active") == 'true' and \
                   resource.getAttribute("role") == 'Started'

        return [r for r in resources if active(r)]

    def find_resource(self, resource_id, exact_match=True):
        """

        :param resource_id: name of the resource
        :param exact_match: if False - return any resource whose name
        contains the :resource_id
        :return:
        """
        TAG = "resource"
        match = "exact " if exact_match else ""
        LOG.debug("find " + match + "match for resource %s" % resource_id)
        x_list = self._find_in_tree(self.cluster, TAG, resource_id,
                                    exact=exact_match)
        return x_list

    # @ssh_cmds.cli_choice(parser="pcs", handler="action")
    # def cluster_nodes(self):
    #     out = self.cluster.get("nodes")["node"]
    #     return json.dumps(out)
