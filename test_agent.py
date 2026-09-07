from agent import donor_agent


donors = ["D001", "D002", "D003", "D004", "D005", "D006"]

for donor_id in donors:
    print(f"\n{'=' * 50}")
    print(f"Testing {donor_id}")
    print(f"{'=' * 50}")

    donor_agent(
        f"""
        Analyze donor {donor_id}.

        Inspect the donor and their history using the available tools.
        Determine the single most appropriate next action.

        Return only the required structured decision summary.
        """
    )