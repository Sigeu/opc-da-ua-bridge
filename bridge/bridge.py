import json
import os
import sys
import queue
import csv
import logging
from datetime import datetime

import opcua
from opcua import ua
import OpenOPC


def get_config_path():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config.json")


def load_config():
    path = get_config_path()
    if not os.path.exists(path):
        logging.error(f"config.json not found at {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    level = cfg.get("log_level", "INFO").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format=LOG_FORMAT, force=True)
    logging.info(f"Loaded config from {path}, log_level={level}")
    return cfg


def write_tag_table_csv(csv_path, tag_infos):
    if not tag_infos:
        logging.warning("No tags to write")
        return
    fieldnames = list(tag_infos[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tag_infos)
    logging.info(f"Tag table written to {csv_path}")


DTYPE_MAP = {
    1: "INT8",
    2: "INT16",
    3: "INT32",
    4: "FLOAT",
    5: "DOUBLE",
    7: "STRING",
    8: "STRING",
    11: "BOOL",
    16: "INT8",
    17: "UINT8",
    18: "UINT16",
    19: "UINT32",
    20: "INT64",
    21: "UINT64",
}

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def DARead(da_client, group_name):
    tags = [tag for tag in da_client.list(flat=True) if tag.startswith(group_name)]
    if not tags:
        return {}, {}, {}

    opcua_tagname_list = [tag[tag.rfind('.') + 1:] for tag in tags]
    values_lst = [(value, timestamp) for name, value, quality, timestamp in da_client.read(tags)]
    access_lst = [acc for name, acc in da_client.properties(tags, id=5)]
    dtypes_lst = [dtype for name, dtype in da_client.properties(tags, id=1)]

    values = dict(zip(opcua_tagname_list, values_lst))
    accesss = dict(zip(opcua_tagname_list, access_lst))
    dtypes = dict(zip(opcua_tagname_list, dtypes_lst))
    return values, accesss, dtypes


def opcua_setup(object_name: str, endpoint: str, namespace_url: str):
    opcua_server = opcua.Server()
    opcua_server.set_endpoint(endpoint)
    index = opcua_server.register_namespace(namespace_url)
    objects_node = opcua_server.get_objects_node()
    obj = objects_node.add_object(index, object_name)
    return index, opcua_server, obj


def ua_tag_create(obj: opcua.Node, index: int, opcua_tag_dict: dict, access_dict: dict,
                  subscription: opcua.Subscription, dtype_dict: dict, ua_r_and_rw: dict):
    dtype_mapping = {
        '2': ua.NodeId(ua.ObjectIds.Int16),
        '3': ua.NodeId(ua.ObjectIds.Int32),
        '4': ua.NodeId(ua.ObjectIds.Float),
        '5': ua.NodeId(ua.ObjectIds.Double),
        '7': ua.NodeId(ua.ObjectIds.DateTime),
        '8': ua.NodeId(ua.ObjectIds.String),
        '11': ua.NodeId(ua.ObjectIds.Boolean),
        '14': ua.NodeId(ua.ObjectIds.Decimal),
        '16': ua.NodeId(ua.ObjectIds.SByte),
        '17': ua.NodeId(ua.ObjectIds.Byte),
        '18': ua.NodeId(ua.ObjectIds.UInt16),
        '19': ua.NodeId(ua.ObjectIds.UInt32),
        '20': ua.NodeId(ua.ObjectIds.Int64),
        '21': ua.NodeId(ua.ObjectIds.UInt64)
    }
    for ua_tagname in access_dict.keys():
        if ua_tagname not in opcua_tag_dict.keys():
            dtype = dtype_mapping.get(str(dtype_dict.get(ua_tagname, 8)), ua.NodeId(ua.ObjectIds.String))
            new_var = obj.add_variable(index, ua_tagname, val=0, datatype=dtype)
            if access_dict[ua_tagname] in ('Read/Write', 'Write'):
                new_var.set_writable()
                subscription.subscribe_data_change(new_var)
                if access_dict[ua_tagname] == 'Read/Write':
                    ua_r_and_rw.update({ua_tagname: new_var})
            else:
                ua_r_and_rw.update({ua_tagname: new_var})
            opcua_tag_dict.update({ua_tagname: new_var})
            logging.info(f"Created UA tag: {ua_tagname}")


class OPCUAHandler:
    def __init__(self, opcua_tags: dict, group_name: str):
        self.opcua_tags = opcua_tags
        self.group_name = group_name
        self.queue = queue.Queue()

    def datachange_notification(self, node: opcua.Node, val, data):
        for ua_tagname, tag in list(self.opcua_tags.items()):
            if tag == node:
                da_tagname = f'{self.group_name}.{ua_tagname}'
                self.queue.put((ua_tagname, da_tagname, val))


def UA2DA_Write(UAHandler: OPCUAHandler, da_client: OpenOPC.client, ua_last_write: dict, da_last_read: dict):
    if not UAHandler.queue.empty():
        try:
            ua_tagname, da_tagname, value = UAHandler.queue.get(timeout=0.1)
            if value != da_last_read.get(ua_tagname, None):
                da_client.write((da_tagname, value))
                ua_last_write.update({ua_tagname: value})
                logging.info(f"WRITE UA -> DA: {ua_tagname} = {value}")
        except Exception as e:
            logging.warning(f"UA->DA write error: {e}")


def DA2UAWrite(ua_r_and_rw: dict, values, ua_last_write: dict, da_last_read: dict):
    for ua_tagname, tag in ua_r_and_rw.items():
        if ua_tagname not in values:
            continue
        try:
            if ua_tagname in ua_last_write.keys():
                if values[ua_tagname][0] != ua_last_write[ua_tagname]:
                    timestamp = datetime.fromisoformat(values[ua_tagname][1])
                    tag.set_value(ua.DataValue(variant=values[ua_tagname][0],
                                               serverTimestamp=datetime.now(),
                                               sourceTimestamp=timestamp))
                    logging.info(f"WRITE DA -> UA: {ua_tagname} = {values[ua_tagname][0]}")
            elif da_last_read.get(ua_tagname, None) != values[ua_tagname][0]:
                timestamp = datetime.fromisoformat(values[ua_tagname][1])
                tag.set_value(ua.DataValue(variant=values[ua_tagname][0],
                                           serverTimestamp=datetime.now(),
                                           sourceTimestamp=timestamp))
                logging.info(f"WRITE DA -> UA: {ua_tagname} = {values[ua_tagname][0]}")
            da_last_read.update({ua_tagname: values[ua_tagname][0]})
        except Exception as e:
            logging.warning(f"DA->UA write error for {ua_tagname}: {e}")


def main():
    CONFIG = load_config()

    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    csv_path = os.path.join(base, "tag_table.csv")

    da_client = OpenOPC.client()
    da_client.connect(CONFIG["da_server"])
    logging.info(f"Connected to OPC DA server: {CONFIG['da_server']}")

    all_tags = da_client.list(flat=True)
    tags = [t for t in all_tags if t.startswith(CONFIG["group_name"])]

    if not tags:
        logging.warning("No tags matched group_name, exporting all tags instead")
        tags = all_tags

    dtypes_lst = [dtype for name, dtype in da_client.properties(tags, id=1)]

    try:
        read_result = da_client.read(tags)
        qualities = {tag: qual for tag, val, qual, ts in read_result}
        has_quality = True
    except Exception:
        logging.warning("Could not read quality for tags, skipping health status")
        has_quality = False

    tag_infos = []
    for i, (da_tag, dtype_id) in enumerate(zip(tags, dtypes_lst)):
        node_id = f"ns=2;i={i + 2}"
        dtype_name = DTYPE_MAP.get(dtype_id, f"UNKNOWN({dtype_id})")
        entry = {
            "NodeId": node_id,
            "TagName": da_tag,
            "DataType": dtype_name,
        }
        if has_quality:
            q = str(qualities.get(da_tag, ""))
            entry["Health"] = "good" if q.lower() == "good" else "bad"
        tag_infos.append(entry)
        logging.info(f"  {node_id:>12}  {dtype_name:>6}  {da_tag}")

    write_tag_table_csv(csv_path, tag_infos)

    index, ua_server, obj = opcua_setup(
        CONFIG["ua_object_name"],
        CONFIG["endpoint"],
        CONFIG["namespace_url"]
    )

    ua_server.start()

    ua_tag_dict = {}
    handler = OPCUAHandler(ua_tag_dict, CONFIG["group_name"])
    subscription = ua_server.create_subscription(500, handler)

    ua_r_and_rw = {}
    ua_last_write = {}
    da_last_read = {}

    try:
        while True:
            UA2DA_Write(handler, da_client, ua_last_write, da_last_read)
            values, accesss, dtypes = DARead(da_client, CONFIG["group_name"])
            if values:
                ua_tag_create(obj, index, ua_tag_dict, accesss, subscription, dtypes, ua_r_and_rw)
                DA2UAWrite(ua_r_and_rw, values, ua_last_write, da_last_read)
    except KeyboardInterrupt:
        logging.info("Shutting down bridge...")
    finally:
        da_client.close()
        ua_server.stop()


if __name__ == "__main__":
    main()
