## Permissions for DRP Collector Development

Collectors are developed using the `drp_collector_dev` MCP server. These
permissions are all allowed:

- Read from websites, for example using `fetch_url_content`
- Read any files in this repo
- Write any files in this repo
- Create temporary working space, for example in `/tmp`, and then read
  and write in there
- Run tests, for example using `python -m pytest`
- Shell commands gauged low risk or read only, for example `grep`
- Python commands gauged low risk or read only

