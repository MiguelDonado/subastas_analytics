1. If the DAG does not succeed we would be alerted (In order to be aware of failure, we are using the paradigm **no news is bad news** and using the service healthchecks.io. If we do not send a ping to the private URL they give us, it means bad news, and they send us an email. We would have to solve the problem, and execute the dag manually for those days).
   1. Computer turned off or failed cron job
   2. Bronze section:
      - Failed task fetch_auctions(): No auctions for the 7 past days would be loaded into bronze layer.
        - Error in fetch_boe_sumario() -> It would give an error, and make the task fetch_auctions() to fail (happens when there is some problem with the BOE API).
        - Error in _parse_auction_candidates() -> It would raise an error, and make the task fetch_auctions() to fail. (happens if for whatever reason the xml schema of the BOE summary changes)
        - Error in is_auction() -> It would make fetch_auctions task to fail. Dag retries each task up to 3 times. If neither succeeds, load_auctions() would not be executed. So, here we are treating the entire operation as a unit. If all the auctions for the 7 past days succeed, then we will insert in bronze layer, otherwise nothing would be inserted. 
        - Error in _fetch_announcement(): It would give an error and make the task fetch_auctions to fail. 
        - Error in get_announcement_boe_ref() or get_announcement_text(), get_announcement_publication_date() it gives an error, and make the task fetch_auctions to fail. (happens if at some point the schema of xml auction announcements changes)
       - Failed task load_auctions(): It cannot fail. If some duplicated auction it does not insert that auction.
    