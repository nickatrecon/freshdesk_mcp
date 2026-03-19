# Freshdesk MCP Server
[![smithery badge](https://smithery.ai/badge/@effytech/freshdesk_mcp)](https://smithery.ai/server/@effytech/freshdesk_mcp)

[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/effytech/freshdesk_mcp)](https://archestra.ai/mcp-catalog/effytech__freshdesk_mcp)

An MCP server implementation that integrates with the Freshdesk API v2, enabling AI models to interact with Freshdesk modules and perform various support operations.

## Features

- **Full Freshdesk API v2 Coverage**: 100+ tools covering tickets, contacts, companies, agents, groups, time entries, satisfaction ratings, knowledge base, discussions, canned responses, and admin endpoints
- **AI Model Support**: Enables AI models to perform support operations through Freshdesk
- **Automated Ticket Management**: Handle ticket creation, updates, replies, notes, merging, forwarding, and bulk operations

## Components

### Tools

The server provides tools organized by Freshdesk module:

#### Tickets

| Tool | Description |
|------|-------------|
| `get_tickets` | List tickets with pagination, filtering (by requester, email, company, date), sorting, and embedded data |
| `get_ticket` | Get a single ticket with optional embedded data (conversations, requester, company, stats, sla_policy) |
| `create_ticket` | Create a ticket with full parameter support (cc, tags, group, agent, product, parent, type, due dates, custom fields) |
| `create_outbound_email_ticket` | Create a ticket via outbound email |
| `update_ticket` | Update any ticket fields |
| `delete_ticket` | Soft-delete a ticket |
| `restore_ticket` | Restore a soft-deleted ticket |
| `search_tickets` | Search tickets with query strings (e.g. `"(status:2 OR status:3) AND priority:4"`) |
| `bulk_update_tickets` | Bulk update multiple tickets at once |
| `bulk_delete_tickets` | Bulk delete multiple tickets |
| `merge_tickets` | Merge secondary tickets into a primary ticket |
| `forward_ticket` | Forward a ticket to external email addresses |
| `get_ticket_watchers` | List watchers on a ticket |
| `watch_ticket` | Add current agent as watcher |
| `unwatch_ticket` | Remove current agent as watcher |
| `get_associated_tickets` | View associated/tracker tickets |
| `get_archived_ticket` | View an archived ticket |
| `delete_archived_ticket` | Delete an archived ticket |
| `get_archived_ticket_conversations` | List conversations on an archived ticket |

#### Ticket Summary

| Tool | Description |
|------|-------------|
| `view_ticket_summary` | Get a ticket's summary |
| `update_ticket_summary` | Update a ticket's summary |
| `delete_ticket_summary` | Delete a ticket's summary |

#### Ticket Fields (Admin)

| Tool | Description |
|------|-------------|
| `get_ticket_fields` | List all ticket fields |
| `get_field_properties` | Get properties of a specific field by name |
| `create_ticket_field` | Create a custom ticket field |
| `view_ticket_field` | View a ticket field |
| `update_ticket_field` | Update a ticket field |
| `delete_ticket_field` | Delete a custom ticket field |

#### Conversations (Replies & Notes)

| Tool | Description |
|------|-------------|
| `get_ticket_conversation` | List all conversations for a ticket |
| `create_ticket_reply` | Reply to a ticket (with cc, bcc, from_email support) |
| `reply_to_forward` | Reply to a forwarded ticket |
| `create_ticket_note` | Add a note (private/public, with notifications) |
| `update_ticket_conversation` | Update a conversation entry |
| `delete_conversation` | Delete a conversation entry |

#### Contacts

| Tool | Description |
|------|-------------|
| `list_contacts` | List contacts with filtering (email, mobile, phone, company, state, updated_since) |
| `get_contact` | Get a single contact |
| `create_contact` | Create a new contact |
| `update_contact` | Update a contact |
| `delete_contact` | Soft-delete a contact |
| `hard_delete_contact` | Permanently delete a contact (GDPR) |
| `restore_contact` | Restore a soft-deleted contact |
| `make_agent` | Convert a contact into an agent |
| `send_invite` | Send a portal invite to a contact |
| `merge_contacts` | Merge contacts together |
| `export_contacts` | Start a contact export |
| `get_contact_export` | Get export status/data |
| `search_contacts` | Autocomplete search for contacts |
| `search_contacts_by_query` | Search contacts with full query string |

#### Contact Fields

| Tool | Description |
|------|-------------|
| `list_contact_fields` | List all contact fields |
| `view_contact_field` | View a contact field |
| `create_contact_field` | Create a contact field |
| `update_contact_field` | Update a contact field |

#### Companies

| Tool | Description |
|------|-------------|
| `list_companies` | List companies with pagination |
| `view_company` | Get a single company |
| `create_company` | Create a new company |
| `update_company` | Update a company |
| `delete_company` | Delete a company |
| `search_companies` | Search companies by name (autocomplete) |
| `search_companies_by_query` | Search companies with full query string |
| `filter_companies` | Filter companies |
| `find_company_by_name` | Find a company by exact name |
| `list_company_fields` | List all company fields |

#### Agents

| Tool | Description |
|------|-------------|
| `get_agents` | List agents with filtering (email, mobile, phone, state) |
| `view_agent` | View a single agent |
| `get_current_agent` | Get the currently authenticated agent |
| `create_agent` | Create an agent |
| `update_agent` | Update an agent |
| `delete_agent` | Delete an agent |
| `forget_agent` | Permanently forget an agent (GDPR) |
| `reactivate_agent` | Reactivate a deactivated agent |
| `convert_agent_to_requester` | Convert an agent to a requester |
| `search_agents` | Autocomplete search for agents |

#### Groups

| Tool | Description |
|------|-------------|
| `list_groups` | List groups with pagination |
| `view_group` | View a single group |
| `create_group` | Create a group |
| `update_group` | Update a group |
| `delete_group` | Delete a group |

#### Time Entries

| Tool | Description |
|------|-------------|
| `create_time_entry` | Create a time entry for a ticket |
| `list_time_entries_for_ticket` | List time entries for a specific ticket |
| `list_all_time_entries` | List all time entries |
| `update_time_entry` | Update a time entry |
| `toggle_timer` | Start/stop a timer on a time entry |
| `delete_time_entry` | Delete a time entry |

#### Satisfaction Ratings

| Tool | Description |
|------|-------------|
| `create_satisfaction_rating` | Create a satisfaction rating for a ticket |
| `list_satisfaction_ratings_for_ticket` | List ratings for a ticket |
| `list_all_satisfaction_ratings` | List all satisfaction ratings |

#### Canned Responses

| Tool | Description |
|------|-------------|
| `list_canned_response_folders` | List all canned response folders |
| `view_canned_response_folder` | View a folder |
| `create_canned_response_folder` | Create a folder |
| `update_canned_response_folder` | Update a folder |
| `list_canned_responses` | List responses in a folder |
| `view_canned_response` | View a canned response |
| `create_canned_response` | Create a canned response |
| `update_canned_response` | Update a canned response |
| `delete_canned_response` | Delete a canned response |

#### Solutions (Knowledge Base)

| Tool | Description |
|------|-------------|
| `list_solution_categories` | List all solution categories |
| `view_solution_category` | View a category |
| `create_solution_category` | Create a category |
| `update_solution_category` | Update a category |
| `delete_solution_category` | Delete a category |
| `list_solution_folders` | List folders in a category |
| `view_solution_folder` | View a folder |
| `create_solution_folder` | Create a folder |
| `update_solution_folder` | Update a folder |
| `delete_solution_folder` | Delete a folder |
| `list_solution_subfolders` | List subfolders |
| `list_solution_articles` | List articles in a folder |
| `view_solution_article` | View an article |
| `create_solution_article` | Create an article |
| `update_solution_article` | Update an article |
| `delete_solution_article` | Delete an article |
| `search_solution_articles` | Search articles by keyword |

#### Discussions (Forums)

| Tool | Description |
|------|-------------|
| `list_discussion_categories` | List all discussion categories |
| `view_discussion_category` | View a category |
| `create_discussion_category` | Create a category |
| `update_discussion_category` | Update a category |
| `delete_discussion_category` | Delete a category |
| `list_discussion_forums` | List forums in a category |
| `view_discussion_forum` | View a forum |
| `create_discussion_forum` | Create a forum |
| `update_discussion_forum` | Update a forum |
| `delete_discussion_forum` | Delete a forum |
| `list_discussion_topics` | List topics in a forum |
| `view_discussion_topic` | View a topic |
| `create_discussion_topic` | Create a topic |
| `update_discussion_topic` | Update a topic |
| `delete_discussion_topic` | Delete a topic |
| `create_discussion_comment` | Comment on a topic |
| `update_discussion_comment` | Update a comment |
| `delete_discussion_comment` | Delete a comment |

#### Admin & Configuration

| Tool | Description |
|------|-------------|
| `list_roles` | List all roles |
| `view_role` | View a role |
| `list_products` | List all products |
| `view_product` | View a product |
| `create_product` | Create a product |
| `update_product` | Update a product |
| `list_email_configs` | List email configurations |
| `view_email_config` | View an email configuration |
| `list_sla_policies` | List SLA policies |
| `create_sla_policy` | Create an SLA policy |
| `update_sla_policy` | Update an SLA policy |
| `list_business_hours` | List business hours configs |
| `view_business_hours` | View business hours |
| `list_ticket_forms` | List ticket forms |
| `view_ticket_form` | View a ticket form |
| `create_ticket_form` | Create a ticket form |
| `update_ticket_form` | Update a ticket form |
| `delete_ticket_form` | Delete a ticket form |
| `delete_attachment` | Delete an attachment |

### Prompts

| Prompt | Description |
|--------|-------------|
| `create_ticket` | Guided ticket creation with field lookup guidance |
| `create_reply` | Guided ticket reply with conversation context matching |

## Getting Started

### Installing via Smithery

To install freshdesk_mcp for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@effytech/freshdesk_mcp):

```bash
npx -y @smithery/cli install @effytech/freshdesk_mcp --client claude
```

### Prerequisites

- A Freshdesk account (sign up at [freshdesk.com](https://freshdesk.com))
- Freshdesk API key
- `uvx` installed (`pip install uv` or `brew install uv`)

### Configuration

1. Generate your Freshdesk API key from the Freshdesk admin panel
2. Set up your domain and authentication details

### Usage with Claude Desktop

1. Install Claude Desktop if you haven't already
2. Add the following configuration to your `claude_desktop_config.json`:

```json
"mcpServers": {
  "freshdesk-mcp": {
    "command": "uvx",
    "args": [
        "freshdesk-mcp"
    ],
    "env": {
      "FRESHDESK_API_KEY": "<YOUR_FRESHDESK_API_KEY>",
      "FRESHDESK_DOMAIN": "<YOUR_FRESHDESK_DOMAIN>"
    }
  }
}
```

### Usage with Claude Code

```bash
claude mcp add freshdesk-mcp -e FRESHDESK_API_KEY=YOUR_KEY -e FRESHDESK_DOMAIN=YOUR_DOMAIN -- uv run freshdesk-mcp
```

Verify with `/mcp` inside Claude Code.

**Important Notes**:
- Replace `YOUR_FRESHDESK_API_KEY` with your actual Freshdesk API key
- Replace `YOUR_FRESHDESK_DOMAIN` with your Freshdesk domain (e.g., `yourcompany.freshdesk.com`)

## Example Operations

Once configured, you can ask Claude to perform operations like:

- "Create a new ticket with subject 'Payment Issue for customer A101' and description as 'Reaching out for a payment issue in the last month for customer A101', where customer email is a101@acme.com and set priority to high"
- "Update the status of ticket #12345 to 'Resolved'"
- "List all high-priority tickets assigned to the agent John Doe"
- "List previous tickets of customer A101 in last 30 days"
- "Log 2 hours of billable time on ticket #456"
- "Search the knowledge base for articles about password reset"
- "Merge tickets #100, #101, and #102 into ticket #99"
- "Forward ticket #200 to partner@external.com"
- "Show all satisfaction ratings from this week"

## Testing

For testing purposes, you can start the server manually:

```bash
uvx freshdesk-mcp --env FRESHDESK_API_KEY=<your_api_key> --env FRESHDESK_DOMAIN=<your_domain>
```

## Troubleshooting

- Verify your Freshdesk API key and domain are correct
- Ensure proper network connectivity to Freshdesk servers
- Check API rate limits and quotas (Growth: 200/min, Pro: 400/min, Enterprise: 700/min)
- Verify the `uvx` command is available in your PATH

## License

This MCP server is licensed under the MIT License. See the LICENSE file in the project repository for full details.
