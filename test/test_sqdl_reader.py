from core_tools.data.sqdl import init_sqdl, sqdl_query, load_by_uuid


def main():
    init_sqdl("Test")
    records = sqdl_query()

    for r in records:
        ds = load_by_uuid(r.uuid)
        print("--- new dataset ---")
        print("dataset name: {}".format(ds.exp_name))
        print("dataset uuid: {}".format(ds.exp_uuid))
        print("dataset timestamp: {}".format(ds.run_timestamp))


if __name__ == "__main__":
    main()
