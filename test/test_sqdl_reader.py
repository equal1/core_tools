from core_tools.data.sqdl import init_sqdl, sqdl_query, load_by_uuid


def main():
    init_sqdl("Test")
    records = sqdl_query()

    for r in records:
        ds = load_by_uuid(r.uuid)
        print("--- new dataset ---")
        print(f"dataset name: {ds.exp_name}")
        print(f"dataset uuid: {ds.exp_uuid}")
        print(f"dataset timestamp: {ds.run_timestamp}")


if __name__ == "__main__":
    main()
