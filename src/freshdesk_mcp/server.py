import httpx
from mcp.server.fastmcp import FastMCP
import logging
import os
import base64
from typing import Optional, Dict, Union, Any, List
from enum import IntEnum, Enum
import re
from pydantic import BaseModel, Field

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize FastMCP server
mcp = FastMCP("freshdesk-mcp")

FRESHDESK_API_KEY = os.getenv("FRESHDESK_API_KEY")
FRESHDESK_DOMAIN = os.getenv("FRESHDESK_DOMAIN")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _headers(content_type: bool = True) -> Dict[str, str]:
    """Return authorization headers for the Freshdesk API."""
    h = {
        "Authorization": f"Basic {base64.b64encode(f'{FRESHDESK_API_KEY}:X'.encode()).decode()}"
    }
    if content_type:
        h["Content-Type"] = "application/json"
    return h


def _url(path: str) -> str:
    """Build a full Freshdesk API URL from a relative path."""
    return f"https://{FRESHDESK_DOMAIN}/api/v2/{path}"


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Any] = None,
) -> Any:
    """Execute an HTTP request against the Freshdesk API and return the parsed response."""
    async with httpx.AsyncClient() as client:
        kwargs: Dict[str, Any] = {"headers": _headers()}
        if params is not None:
            kwargs["params"] = params
        if json is not None:
            kwargs["json"] = json
        response = await getattr(client, method)(_url(path), **kwargs)
        response.raise_for_status()
        if response.status_code == 204:
            return {"success": True, "message": "Operation completed successfully"}
        return response.json()


def parse_link_header(link_header: str) -> Dict[str, Optional[int]]:
    """Parse the Link header to extract pagination information."""
    pagination: Dict[str, Optional[int]] = {"next": None, "prev": None}
    if not link_header:
        return pagination
    for link in link_header.split(','):
        match = re.search(r'<(.+?)>;\s*rel="(.+?)"', link)
        if match:
            url, rel = match.groups()
            page_match = re.search(r'page=(\d+)', url)
            if page_match:
                pagination[rel] = int(page_match.group(1))
    return pagination


async def _paginated_get(path: str, page: int = 1, per_page: int = 30, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET with pagination metadata extracted from Link headers."""
    if page < 1:
        return {"error": "Page number must be greater than 0"}
    if per_page < 1 or per_page > 100:
        return {"error": "Page size must be between 1 and 100"}
    p = {"page": page, "per_page": per_page}
    if params:
        p.update(params)
    async with httpx.AsyncClient() as client:
        response = await client.get(_url(path), headers=_headers(), params=p)
        response.raise_for_status()
        link_header = response.headers.get('Link', '')
        pagination_info = parse_link_header(link_header)
        return {
            "data": response.json(),
            "pagination": {
                "current_page": page,
                "next_page": pagination_info.get("next"),
                "prev_page": pagination_info.get("prev"),
                "per_page": per_page,
            },
        }


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TicketSource(IntEnum):
    EMAIL = 1
    PORTAL = 2
    PHONE = 3
    CHAT = 7
    FEEDBACK_WIDGET = 9
    OUTBOUND_EMAIL = 10


class TicketStatus(IntEnum):
    OPEN = 2
    PENDING = 3
    RESOLVED = 4
    CLOSED = 5


class TicketPriority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class AgentTicketScope(IntEnum):
    GLOBAL_ACCESS = 1
    GROUP_ACCESS = 2
    RESTRICTED_ACCESS = 3


class UnassignedForOptions(str, Enum):
    THIRTY_MIN = "30m"
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    FOUR_HOURS = "4h"
    EIGHT_HOURS = "8h"
    TWELVE_HOURS = "12h"
    ONE_DAY = "1d"
    TWO_DAYS = "2d"
    THREE_DAYS = "3d"


# ---------------------------------------------------------------------------
# Pydantic models for validation
# ---------------------------------------------------------------------------

class GroupCreate(BaseModel):
    name: str = Field(..., description="Name of the group")
    description: Optional[str] = Field(None, description="Description of the group")
    agent_ids: Optional[List[int]] = Field(default=None, description="Array of agent user ids")
    auto_ticket_assign: Optional[int] = Field(default=0, ge=0, le=1, description="Automatic ticket assignment type (0 or 1)")
    escalate_to: Optional[int] = Field(None, description="User ID to whom escalation email is sent if ticket is unassigned")
    unassigned_for: Optional[UnassignedForOptions] = Field(default=UnassignedForOptions.THIRTY_MIN, description="Time after which escalation email will be sent")


class ContactFieldCreate(BaseModel):
    label: str = Field(..., description="Display name for the field (as seen by agents)")
    label_for_customers: str = Field(..., description="Display name for the field (as seen by customers)")
    type: str = Field(
        ...,
        description="Type of the field",
        pattern="^(custom_text|custom_paragraph|custom_checkbox|custom_number|custom_dropdown|custom_phone_number|custom_url|custom_date)$",
    )
    editable_in_signup: bool = Field(default=False, description="Set to true if the field can be updated by customers during signup")
    position: int = Field(default=1, description="Position of the company field")
    required_for_agents: bool = Field(default=False, description="Set to true if the field is mandatory for agents")
    customers_can_edit: bool = Field(default=False, description="Set to true if the customer can edit the fields in the customer portal")
    required_for_customers: bool = Field(default=False, description="Set to true if the field is mandatory in the customer portal")
    displayed_for_customers: bool = Field(default=False, description="Set to true if the customers can see the field in the customer portal")
    choices: Optional[List[Dict[str, Union[str, int]]]] = Field(default=None, description="Array of objects in format {'value': 'Choice text', 'position': 1} for dropdown choices")


class CannedResponseCreate(BaseModel):
    title: str = Field(..., description="Title of the canned response")
    content_html: str = Field(..., description="HTML version of the canned response content")
    folder_id: int = Field(..., description="Folder where the canned response gets added")
    visibility: int = Field(..., description="Visibility of the canned response (0=all agents, 1=personal, 2=select groups)", ge=0, le=2)
    group_ids: Optional[List[int]] = Field(None, description="Groups for which the canned response is visible. Required if visibility=2")


# ===========================================================================
# TICKET TOOLS
# ===========================================================================

@mcp.tool()
async def get_ticket_fields() -> Any:
    """Get all ticket fields from Freshdesk."""
    return await _request("get", "ticket_fields")


@mcp.tool()
async def get_tickets(
    page: Optional[int] = 1,
    per_page: Optional[int] = 30,
    filter: Optional[str] = None,
    requester_id: Optional[int] = None,
    email: Optional[str] = None,
    company_id: Optional[int] = None,
    updated_since: Optional[str] = None,
    include: Optional[str] = None,
    order_by: Optional[str] = None,
    order_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Get tickets from Freshdesk with pagination and filtering support.

    Args:
        page: Page number (default 1)
        per_page: Results per page, 1-100 (default 30)
        filter: Predefined filter - new_and_my_open, watching, spam, deleted
        requester_id: Filter by requester ID
        email: Filter by requester email
        company_id: Filter by company ID
        updated_since: Return tickets updated after this datetime (ISO 8601)
        include: Embed additional info - requester, company, stats, description
        order_by: Sort field - created_at, due_by, updated_at, status
        order_type: Sort direction - asc or desc
    """
    params: Dict[str, Any] = {}
    if filter:
        params["filter"] = filter
    if requester_id:
        params["requester_id"] = requester_id
    if email:
        params["email"] = email
    if company_id:
        params["company_id"] = company_id
    if updated_since:
        params["updated_since"] = updated_since
    if include:
        params["include"] = include
    if order_by:
        params["order_by"] = order_by
    if order_type:
        params["order_type"] = order_type
    return await _paginated_get("tickets", page=page, per_page=per_page, params=params)


@mcp.tool()
async def get_ticket(ticket_id: int, include: Optional[str] = None) -> Any:
    """Get a single ticket from Freshdesk.

    Args:
        ticket_id: The ticket ID
        include: Embed additional info - conversations, requester, company, stats, sla_policy
    """
    params = {}
    if include:
        params["include"] = include
    return await _request("get", f"tickets/{ticket_id}", params=params or None)


@mcp.tool()
async def create_ticket(
    subject: str,
    description: str,
    source: Union[int, str],
    priority: Union[int, str],
    status: Union[int, str],
    email: Optional[str] = None,
    requester_id: Optional[int] = None,
    phone: Optional[str] = None,
    cc_emails: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    group_id: Optional[int] = None,
    responder_id: Optional[int] = None,
    company_id: Optional[int] = None,
    product_id: Optional[int] = None,
    parent_id: Optional[int] = None,
    type: Optional[str] = None,
    due_by: Optional[str] = None,
    fr_due_by: Optional[str] = None,
    email_config_id: Optional[int] = None,
    custom_fields: Optional[Dict[str, Any]] = None,
    additional_fields: Optional[Dict[str, Any]] = None,
) -> Any:
    """Create a ticket in Freshdesk.

    Args:
        subject: Ticket subject
        description: HTML content of the ticket
        source: 1=Email, 2=Portal, 3=Phone, 7=Chat, 9=Feedback Widget, 10=Outbound Email
        priority: 1=Low, 2=Medium, 3=High, 4=Urgent
        status: 2=Open, 3=Pending, 4=Resolved, 5=Closed
        email: Requester email (required if no requester_id or phone)
        requester_id: ID of the requester
        phone: Phone number of the requester
        cc_emails: CC email addresses
        tags: Tags for the ticket
        group_id: ID of the group to assign
        responder_id: ID of the agent to assign
        company_id: Company ID of the requester
        product_id: ID of the product
        parent_id: Parent ticket ID (for child tickets)
        type: Ticket type (standard field, not custom)
        due_by: Due date timestamp (ISO 8601)
        fr_due_by: First response due date (ISO 8601)
        email_config_id: ID of email config for outbound email
        custom_fields: Custom field key-value pairs
        additional_fields: Any other top-level fields to include
    """
    if not email and not requester_id and not phone:
        return {"error": "Either email, requester_id, or phone must be provided"}

    try:
        source_val = int(source)
        priority_val = int(priority)
        status_val = int(status)
    except ValueError:
        return {"error": "Invalid value for source, priority, or status"}

    if source_val not in [e.value for e in TicketSource]:
        return {"error": f"Invalid source. Must be one of: {[e.value for e in TicketSource]}"}
    if priority_val not in [e.value for e in TicketPriority]:
        return {"error": f"Invalid priority. Must be one of: {[e.value for e in TicketPriority]}"}
    if status_val not in [e.value for e in TicketStatus]:
        return {"error": f"Invalid status. Must be one of: {[e.value for e in TicketStatus]}"}

    data: Dict[str, Any] = {
        "subject": subject,
        "description": description,
        "source": source_val,
        "priority": priority_val,
        "status": status_val,
    }

    if email:
        data["email"] = email
    if requester_id:
        data["requester_id"] = requester_id
    if phone:
        data["phone"] = phone
    if cc_emails:
        data["cc_emails"] = cc_emails
    if tags:
        data["tags"] = tags
    if group_id:
        data["group_id"] = group_id
    if responder_id:
        data["responder_id"] = responder_id
    if company_id:
        data["company_id"] = company_id
    if product_id:
        data["product_id"] = product_id
    if parent_id:
        data["parent_id"] = parent_id
    if type:
        data["type"] = type
    if due_by:
        data["due_by"] = due_by
    if fr_due_by:
        data["fr_due_by"] = fr_due_by
    if email_config_id:
        data["email_config_id"] = email_config_id
    if custom_fields:
        data["custom_fields"] = custom_fields
    if additional_fields:
        data.update(additional_fields)

    return await _request("post", "tickets", json=data)


@mcp.tool()
async def create_outbound_email_ticket(
    subject: str,
    description: str,
    email: str,
    priority: Union[int, str],
    status: Union[int, str],
    email_config_id: Optional[int] = None,
    cc_emails: Optional[List[str]] = None,
    custom_fields: Optional[Dict[str, Any]] = None,
) -> Any:
    """Create a ticket via outbound email in Freshdesk.

    Args:
        subject: Ticket subject
        description: HTML content
        email: Requester email
        priority: 1=Low, 2=Medium, 3=High, 4=Urgent
        status: 2=Open, 3=Pending, 4=Resolved, 5=Closed
        email_config_id: ID of the email config to use
        cc_emails: CC email addresses
        custom_fields: Custom field key-value pairs
    """
    data: Dict[str, Any] = {
        "subject": subject,
        "description": description,
        "email": email,
        "priority": int(priority),
        "status": int(status),
    }
    if email_config_id:
        data["email_config_id"] = email_config_id
    if cc_emails:
        data["cc_emails"] = cc_emails
    if custom_fields:
        data["custom_fields"] = custom_fields
    return await _request("post", "tickets/outbound_email", json=data)


@mcp.tool()
async def update_ticket(ticket_id: int, ticket_fields: Dict[str, Any]) -> Any:
    """Update a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID
        ticket_fields: Fields to update (e.g. status, priority, group_id, custom_fields, etc.)
    """
    if not ticket_fields:
        return {"error": "No fields provided for update"}
    return await _request("put", f"tickets/{ticket_id}", json=ticket_fields)


@mcp.tool()
async def delete_ticket(ticket_id: int) -> Any:
    """Soft-delete a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID to delete
    """
    return await _request("delete", f"tickets/{ticket_id}")


@mcp.tool()
async def restore_ticket(ticket_id: int) -> Any:
    """Restore a soft-deleted ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID to restore
    """
    return await _request("put", f"tickets/{ticket_id}/restore")


@mcp.tool()
async def bulk_update_tickets(ticket_ids: List[int], properties: Dict[str, Any]) -> Any:
    """Bulk update multiple tickets in Freshdesk.

    Args:
        ticket_ids: List of ticket IDs to update
        properties: Fields to update on all tickets (e.g. status, priority, group_id)
    """
    data = {"ids": ticket_ids, "properties": properties}
    return await _request("post", "tickets/bulk_update", json=data)


@mcp.tool()
async def bulk_delete_tickets(ticket_ids: List[int]) -> Any:
    """Bulk delete multiple tickets in Freshdesk.

    Args:
        ticket_ids: List of ticket IDs to delete
    """
    data = {"ids": ticket_ids}
    return await _request("post", "tickets/bulk_delete", json=data)


@mcp.tool()
async def search_tickets(query: str) -> Any:
    """Search for tickets in Freshdesk using a query string.

    Args:
        query: Search query, e.g. "(status:2 OR status:3) AND priority:4"
    """
    return await _request("get", "search/tickets", params={"query": query})


@mcp.tool()
async def merge_tickets(primary_id: int, ticket_ids: List[int]) -> Any:
    """Merge secondary tickets into a primary ticket.

    Args:
        primary_id: The primary ticket ID that will remain
        ticket_ids: List of ticket IDs to merge into the primary
    """
    data = {"primary_id": primary_id, "ticket_ids": ticket_ids}
    return await _request("put", "tickets/merge", json=data)


@mcp.tool()
async def forward_ticket(ticket_id: int, body: str, to_emails: List[str], cc_emails: Optional[List[str]] = None, bcc_emails: Optional[List[str]] = None) -> Any:
    """Forward a ticket to external email addresses.

    Args:
        ticket_id: The ticket ID to forward
        body: HTML body of the forwarded message
        to_emails: List of email addresses to forward to
        cc_emails: Optional CC email addresses
        bcc_emails: Optional BCC email addresses
    """
    data: Dict[str, Any] = {"body": body, "to_emails": to_emails}
    if cc_emails:
        data["cc_emails"] = cc_emails
    if bcc_emails:
        data["bcc_emails"] = bcc_emails
    return await _request("post", f"tickets/{ticket_id}/forward", json=data)


@mcp.tool()
async def get_ticket_watchers(ticket_id: int) -> Any:
    """List all watchers on a ticket.

    Args:
        ticket_id: The ticket ID
    """
    return await _request("get", f"tickets/{ticket_id}/watchers")


@mcp.tool()
async def watch_ticket(ticket_id: int) -> Any:
    """Add the current agent as a watcher on a ticket.

    Args:
        ticket_id: The ticket ID to watch
    """
    return await _request("post", f"tickets/{ticket_id}/watch")


@mcp.tool()
async def unwatch_ticket(ticket_id: int) -> Any:
    """Remove the current agent as a watcher from a ticket.

    Args:
        ticket_id: The ticket ID to unwatch
    """
    return await _request("put", f"tickets/{ticket_id}/unwatch")


@mcp.tool()
async def get_associated_tickets(ticket_id: int) -> Any:
    """View tickets associated with a given ticket (e.g. tracker tickets).

    Args:
        ticket_id: The ticket ID
    """
    return await _request("get", f"tickets/{ticket_id}/associated_tickets")


# --- Archived tickets ---

@mcp.tool()
async def get_archived_ticket(ticket_id: int) -> Any:
    """View an archived ticket.

    Args:
        ticket_id: The archived ticket ID
    """
    return await _request("get", f"tickets/archived/{ticket_id}")


@mcp.tool()
async def delete_archived_ticket(ticket_id: int) -> Any:
    """Delete an archived ticket.

    Args:
        ticket_id: The archived ticket ID
    """
    return await _request("delete", f"tickets/archived/{ticket_id}")


@mcp.tool()
async def get_archived_ticket_conversations(ticket_id: int) -> Any:
    """List conversations on an archived ticket.

    Args:
        ticket_id: The archived ticket ID
    """
    return await _request("get", f"tickets/archived/{ticket_id}/conversations")


# --- Ticket summary ---

@mcp.tool()
async def view_ticket_summary(ticket_id: int) -> Any:
    """Get the summary of a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID
    """
    return await _request("get", f"tickets/{ticket_id}/summary")


@mcp.tool()
async def update_ticket_summary(ticket_id: int, body: str) -> Any:
    """Update the summary of a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID
        body: The summary text
    """
    return await _request("put", f"tickets/{ticket_id}/summary", json={"body": body})


@mcp.tool()
async def delete_ticket_summary(ticket_id: int) -> Any:
    """Delete the summary of a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID
    """
    return await _request("delete", f"tickets/{ticket_id}/summary")


# --- Ticket fields (admin) ---

@mcp.tool()
async def get_field_properties(field_name: str) -> Any:
    """Get properties of a specific ticket field by name.

    Args:
        field_name: The field name (e.g. 'type', 'status', 'priority', or a custom field name)
    """
    actual_field_name = "ticket_type" if field_name == "type" else field_name
    fields = await _request("get", "ticket_fields")
    return next((field for field in fields if field["name"] == actual_field_name), None)


@mcp.tool()
async def create_ticket_field(ticket_field_fields: Dict[str, Any]) -> Any:
    """Create a custom ticket field in Freshdesk.

    Args:
        ticket_field_fields: Field definition (label, type, etc.)
    """
    return await _request("post", "admin/ticket_fields", json=ticket_field_fields)


@mcp.tool()
async def view_ticket_field(ticket_field_id: int) -> Any:
    """View a ticket field in Freshdesk.

    Args:
        ticket_field_id: The ticket field ID
    """
    return await _request("get", f"admin/ticket_fields/{ticket_field_id}")


@mcp.tool()
async def update_ticket_field(ticket_field_id: int, ticket_field_fields: Dict[str, Any]) -> Any:
    """Update a ticket field in Freshdesk.

    Args:
        ticket_field_id: The ticket field ID
        ticket_field_fields: Fields to update
    """
    return await _request("put", f"admin/ticket_fields/{ticket_field_id}", json=ticket_field_fields)


@mcp.tool()
async def delete_ticket_field(ticket_field_id: int) -> Any:
    """Delete a custom ticket field in Freshdesk.

    Args:
        ticket_field_id: The ticket field ID
    """
    return await _request("delete", f"admin/ticket_fields/{ticket_field_id}")


# ===========================================================================
# CONVERSATION TOOLS (Replies & Notes)
# ===========================================================================

@mcp.tool()
async def get_ticket_conversation(ticket_id: int) -> Any:
    """Get all conversations for a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID
    """
    return await _request("get", f"tickets/{ticket_id}/conversations")


@mcp.tool()
async def create_ticket_reply(
    ticket_id: int,
    body: str,
    cc_emails: Optional[List[str]] = None,
    bcc_emails: Optional[List[str]] = None,
    from_email: Optional[str] = None,
) -> Any:
    """Reply to a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID
        body: HTML content of the reply
        cc_emails: CC email addresses
        bcc_emails: BCC email addresses
        from_email: Outgoing email address
    """
    data: Dict[str, Any] = {"body": body}
    if cc_emails:
        data["cc_emails"] = cc_emails
    if bcc_emails:
        data["bcc_emails"] = bcc_emails
    if from_email:
        data["from_email"] = from_email
    return await _request("post", f"tickets/{ticket_id}/reply", json=data)


@mcp.tool()
async def reply_to_forward(ticket_id: int, body: str, to_emails: Optional[List[str]] = None, cc_emails: Optional[List[str]] = None, bcc_emails: Optional[List[str]] = None) -> Any:
    """Reply to a forwarded ticket.

    Args:
        ticket_id: The ticket ID
        body: HTML content of the reply
        to_emails: Recipient emails
        cc_emails: CC email addresses
        bcc_emails: BCC email addresses
    """
    data: Dict[str, Any] = {"body": body}
    if to_emails:
        data["to_emails"] = to_emails
    if cc_emails:
        data["cc_emails"] = cc_emails
    if bcc_emails:
        data["bcc_emails"] = bcc_emails
    return await _request("post", f"tickets/{ticket_id}/reply_to_forward", json=data)


@mcp.tool()
async def create_ticket_note(
    ticket_id: int,
    body: str,
    private: Optional[bool] = True,
    notify_emails: Optional[List[str]] = None,
    incoming: Optional[bool] = None,
) -> Any:
    """Add a note to a ticket in Freshdesk.

    Args:
        ticket_id: The ticket ID
        body: HTML content of the note
        private: True for private note (default True)
        notify_emails: Agent emails to notify
        incoming: Set true for inbound note
    """
    data: Dict[str, Any] = {"body": body, "private": private}
    if notify_emails:
        data["notify_emails"] = notify_emails
    if incoming is not None:
        data["incoming"] = incoming
    return await _request("post", f"tickets/{ticket_id}/notes", json=data)


@mcp.tool()
async def update_ticket_conversation(conversation_id: int, body: str) -> Any:
    """Update a conversation entry (reply or note) in Freshdesk.

    Args:
        conversation_id: The conversation ID
        body: Updated HTML content
    """
    return await _request("put", f"conversations/{conversation_id}", json={"body": body})


@mcp.tool()
async def delete_conversation(conversation_id: int) -> Any:
    """Delete a conversation entry (reply or note) in Freshdesk.

    Args:
        conversation_id: The conversation ID
    """
    return await _request("delete", f"conversations/{conversation_id}")


# ===========================================================================
# CONTACT TOOLS
# ===========================================================================

@mcp.tool()
async def list_contacts(
    page: Optional[int] = 1,
    per_page: Optional[int] = 30,
    email: Optional[str] = None,
    mobile: Optional[str] = None,
    phone: Optional[str] = None,
    company_id: Optional[int] = None,
    state: Optional[str] = None,
    updated_since: Optional[str] = None,
) -> Dict[str, Any]:
    """List all contacts in Freshdesk with pagination and filtering.

    Args:
        page: Page number (default 1)
        per_page: Results per page, 1-100 (default 30)
        email: Filter by email
        mobile: Filter by mobile
        phone: Filter by phone
        company_id: Filter by company ID
        state: Filter by state (verified, unverified, blocked, deleted)
        updated_since: Return contacts updated after this datetime (ISO 8601)
    """
    params: Dict[str, Any] = {}
    if email:
        params["email"] = email
    if mobile:
        params["mobile"] = mobile
    if phone:
        params["phone"] = phone
    if company_id:
        params["company_id"] = company_id
    if state:
        params["state"] = state
    if updated_since:
        params["updated_since"] = updated_since
    return await _paginated_get("contacts", page=page, per_page=per_page, params=params)


@mcp.tool()
async def get_contact(contact_id: int) -> Any:
    """Get a single contact in Freshdesk.

    Args:
        contact_id: The contact ID
    """
    return await _request("get", f"contacts/{contact_id}")


@mcp.tool()
async def create_contact(contact_fields: Dict[str, Any]) -> Any:
    """Create a new contact in Freshdesk.

    Args:
        contact_fields: Contact data. Required: name. Optional: email, phone, mobile, twitter_id,
            unique_external_id, other_emails, company_id, address, description, job_title,
            language, time_zone, tags, other_companies, custom_fields
    """
    if not contact_fields.get("name"):
        return {"error": "Name is required"}
    return await _request("post", "contacts", json=contact_fields)


@mcp.tool()
async def update_contact(contact_id: int, contact_fields: Dict[str, Any]) -> Any:
    """Update a contact in Freshdesk.

    Args:
        contact_id: The contact ID
        contact_fields: Fields to update
    """
    return await _request("put", f"contacts/{contact_id}", json=contact_fields)


@mcp.tool()
async def delete_contact(contact_id: int) -> Any:
    """Soft-delete a contact in Freshdesk.

    Args:
        contact_id: The contact ID
    """
    return await _request("delete", f"contacts/{contact_id}")


@mcp.tool()
async def hard_delete_contact(contact_id: int) -> Any:
    """Permanently delete a contact in Freshdesk (GDPR). Cannot be undone.

    Args:
        contact_id: The contact ID
    """
    return await _request("delete", f"contacts/{contact_id}/hard_delete")


@mcp.tool()
async def restore_contact(contact_id: int) -> Any:
    """Restore a soft-deleted contact in Freshdesk.

    Args:
        contact_id: The contact ID
    """
    return await _request("put", f"contacts/{contact_id}/restore")


@mcp.tool()
async def make_agent(contact_id: int) -> Any:
    """Convert a contact into an agent in Freshdesk.

    Args:
        contact_id: The contact ID to convert
    """
    return await _request("put", f"contacts/{contact_id}/make_agent")


@mcp.tool()
async def send_invite(contact_id: int) -> Any:
    """Send a portal invite to a contact in Freshdesk.

    Args:
        contact_id: The contact ID
    """
    return await _request("put", f"contacts/{contact_id}/send_invite")


@mcp.tool()
async def merge_contacts(primary_id: int, secondary_ids: List[int]) -> Any:
    """Merge secondary contacts into a primary contact.

    Args:
        primary_id: The primary contact ID that will remain
        secondary_ids: List of contact IDs to merge into primary
    """
    return await _request("post", "contacts/merge", json={"primary_id": primary_id, "secondary_ids": secondary_ids})


@mcp.tool()
async def export_contacts(filter: Optional[Dict[str, Any]] = None) -> Any:
    """Start a contact export in Freshdesk.

    Args:
        filter: Optional filter criteria for the export
    """
    return await _request("post", "contacts/export", json=filter)


@mcp.tool()
async def get_contact_export(export_id: int) -> Any:
    """Get the status/data of a contact export.

    Args:
        export_id: The export ID
    """
    return await _request("get", f"contacts/export/{export_id}")


@mcp.tool()
async def search_contacts(query: str) -> Any:
    """Search for contacts in Freshdesk using autocomplete.

    Args:
        query: Search term (name or email prefix)
    """
    return await _request("get", "contacts/autocomplete", params={"term": query})


@mcp.tool()
async def search_contacts_by_query(query: str) -> Any:
    """Search for contacts in Freshdesk using a full query string.

    Args:
        query: Search query, e.g. "(email:'user@example.com') AND (company_id:123)"
    """
    return await _request("get", "search/contacts", params={"query": query})


# --- Contact fields ---

@mcp.tool()
async def list_contact_fields() -> Any:
    """List all contact fields in Freshdesk."""
    return await _request("get", "contact_fields")


@mcp.tool()
async def view_contact_field(contact_field_id: int) -> Any:
    """View a contact field in Freshdesk.

    Args:
        contact_field_id: The contact field ID
    """
    return await _request("get", f"contact_fields/{contact_field_id}")


@mcp.tool()
async def create_contact_field(contact_field_fields: Dict[str, Any]) -> Any:
    """Create a contact field in Freshdesk.

    Args:
        contact_field_fields: Field definition (label, label_for_customers, type, etc.)
    """
    try:
        validated = ContactFieldCreate(**contact_field_fields)
        data = validated.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": f"Validation error: {str(e)}"}
    return await _request("post", "contact_fields", json=data)


@mcp.tool()
async def update_contact_field(contact_field_id: int, contact_field_fields: Dict[str, Any]) -> Any:
    """Update a contact field in Freshdesk.

    Args:
        contact_field_id: The contact field ID
        contact_field_fields: Fields to update
    """
    return await _request("put", f"contact_fields/{contact_field_id}", json=contact_field_fields)


# ===========================================================================
# COMPANY TOOLS
# ===========================================================================

@mcp.tool()
async def list_companies(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """List all companies in Freshdesk with pagination support.

    Args:
        page: Page number (default 1)
        per_page: Results per page, 1-100 (default 30)
    """
    return await _paginated_get("companies", page=page, per_page=per_page)


@mcp.tool()
async def view_company(company_id: int) -> Any:
    """Get a single company in Freshdesk.

    Args:
        company_id: The company ID
    """
    return await _request("get", f"companies/{company_id}")


@mcp.tool()
async def create_company(company_fields: Dict[str, Any]) -> Any:
    """Create a new company in Freshdesk.

    Args:
        company_fields: Company data. Required: name. Optional: description, domains, note,
            health_score, account_tier, renewal_date, industry, custom_fields
    """
    if not company_fields.get("name"):
        return {"error": "Name is required"}
    return await _request("post", "companies", json=company_fields)


@mcp.tool()
async def update_company(company_id: int, company_fields: Dict[str, Any]) -> Any:
    """Update a company in Freshdesk.

    Args:
        company_id: The company ID
        company_fields: Fields to update
    """
    return await _request("put", f"companies/{company_id}", json=company_fields)


@mcp.tool()
async def delete_company(company_id: int) -> Any:
    """Delete a company in Freshdesk.

    Args:
        company_id: The company ID
    """
    return await _request("delete", f"companies/{company_id}")


@mcp.tool()
async def search_companies(query: str) -> Any:
    """Search for companies in Freshdesk by name (autocomplete).

    Args:
        query: Company name to search for
    """
    return await _request("get", "companies/autocomplete", params={"name": query})


@mcp.tool()
async def search_companies_by_query(query: str) -> Any:
    """Search for companies in Freshdesk using a full query string.

    Args:
        query: Search query, e.g. "(name:'Acme') AND (industry:'Technology')"
    """
    return await _request("get", "search/companies", params={"query": query})


@mcp.tool()
async def filter_companies(query: str) -> Any:
    """Filter companies in Freshdesk.

    Args:
        query: Filter query string
    """
    return await _request("get", "companies/filter", params={"query": query})


@mcp.tool()
async def find_company_by_name(name: str) -> Any:
    """Find a company by exact name in Freshdesk.

    Args:
        name: The company name to find
    """
    return await _request("get", "companies/autocomplete", params={"name": name})


# --- Company fields ---

@mcp.tool()
async def list_company_fields() -> Any:
    """List all company fields in Freshdesk."""
    return await _request("get", "company_fields")


# ===========================================================================
# AGENT TOOLS
# ===========================================================================

@mcp.tool()
async def get_agents(
    page: Optional[int] = 1,
    per_page: Optional[int] = 30,
    email: Optional[str] = None,
    mobile: Optional[str] = None,
    phone: Optional[str] = None,
    state: Optional[str] = None,
) -> Dict[str, Any]:
    """List all agents in Freshdesk with pagination and filtering.

    Args:
        page: Page number (default 1)
        per_page: Results per page, 1-100 (default 30)
        email: Filter by email
        mobile: Filter by mobile
        phone: Filter by phone
        state: Filter by state (fulltime, occasional)
    """
    params: Dict[str, Any] = {}
    if email:
        params["email"] = email
    if mobile:
        params["mobile"] = mobile
    if phone:
        params["phone"] = phone
    if state:
        params["state"] = state
    return await _paginated_get("agents", page=page, per_page=per_page, params=params)


@mcp.tool()
async def view_agent(agent_id: int) -> Any:
    """View a single agent in Freshdesk.

    Args:
        agent_id: The agent ID
    """
    return await _request("get", f"agents/{agent_id}")


@mcp.tool()
async def get_current_agent() -> Any:
    """Get the currently authenticated agent."""
    return await _request("get", "agents/me")


@mcp.tool()
async def create_agent(agent_fields: Dict[str, Any]) -> Any:
    """Create an agent in Freshdesk.

    Args:
        agent_fields: Agent data. Required: email, ticket_scope (1=Global, 2=Group, 3=Restricted).
            Optional: name, phone, mobile, language, time_zone, group_ids, role_ids,
            occasional, signature, focus_mode
    """
    if not agent_fields.get("email") or not agent_fields.get("ticket_scope"):
        return {"error": "Both 'email' and 'ticket_scope' are required"}
    if agent_fields.get("ticket_scope") not in [e.value for e in AgentTicketScope]:
        return {"error": f"Invalid ticket_scope. Must be one of: {[e.name for e in AgentTicketScope]}"}
    return await _request("post", "agents", json=agent_fields)


@mcp.tool()
async def update_agent(agent_id: int, agent_fields: Dict[str, Any]) -> Any:
    """Update an agent in Freshdesk.

    Args:
        agent_id: The agent ID
        agent_fields: Fields to update
    """
    return await _request("put", f"agents/{agent_id}", json=agent_fields)


@mcp.tool()
async def delete_agent(agent_id: int) -> Any:
    """Delete an agent in Freshdesk.

    Args:
        agent_id: The agent ID
    """
    return await _request("delete", f"agents/{agent_id}")


@mcp.tool()
async def forget_agent(agent_id: int) -> Any:
    """Permanently forget/delete an agent (GDPR compliance).

    Args:
        agent_id: The agent ID
    """
    return await _request("delete", f"agents/{agent_id}/forget")


@mcp.tool()
async def reactivate_agent(agent_id: int) -> Any:
    """Reactivate a deactivated agent.

    Args:
        agent_id: The agent ID
    """
    return await _request("put", f"agents/{agent_id}/reactivate")


@mcp.tool()
async def convert_agent_to_requester(agent_id: int) -> Any:
    """Convert an agent to a requester (contact).

    Args:
        agent_id: The agent ID
    """
    return await _request("put", f"agents/{agent_id}/convert_to_requester")


@mcp.tool()
async def search_agents(query: str) -> Any:
    """Search for agents in Freshdesk using autocomplete.

    Args:
        query: Search term
    """
    return await _request("get", "agents/autocomplete", params={"term": query})


# ===========================================================================
# GROUP TOOLS
# ===========================================================================

@mcp.tool()
async def list_groups(page: Optional[int] = 1, per_page: Optional[int] = 30) -> Dict[str, Any]:
    """List all groups in Freshdesk with pagination.

    Args:
        page: Page number (default 1)
        per_page: Results per page, 1-100 (default 30)
    """
    return await _paginated_get("groups", page=page, per_page=per_page)


@mcp.tool()
async def view_group(group_id: int) -> Any:
    """View a single group in Freshdesk.

    Args:
        group_id: The group ID
    """
    return await _request("get", f"groups/{group_id}")


@mcp.tool()
async def create_group(group_fields: Dict[str, Any]) -> Any:
    """Create a group in Freshdesk.

    Args:
        group_fields: Group data. Required: name. Optional: description, agent_ids,
            auto_ticket_assign, escalate_to, unassigned_for, group_type
    """
    try:
        validated = GroupCreate(**group_fields)
        data = validated.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": f"Validation error: {str(e)}"}
    return await _request("post", "groups", json=data)


@mcp.tool()
async def update_group(group_id: int, group_fields: Dict[str, Any]) -> Any:
    """Update a group in Freshdesk.

    Args:
        group_id: The group ID
        group_fields: Fields to update
    """
    try:
        validated = GroupCreate(**group_fields)
        data = validated.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": f"Validation error: {str(e)}"}
    return await _request("put", f"groups/{group_id}", json=data)


@mcp.tool()
async def delete_group(group_id: int) -> Any:
    """Delete a group in Freshdesk.

    Args:
        group_id: The group ID
    """
    return await _request("delete", f"groups/{group_id}")


# ===========================================================================
# TIME ENTRIES TOOLS
# ===========================================================================

@mcp.tool()
async def create_time_entry(
    ticket_id: int,
    time_spent: str,
    agent_id: Optional[int] = None,
    billable: Optional[bool] = None,
    note: Optional[str] = None,
    executed_at: Optional[str] = None,
    timer_running: Optional[bool] = None,
) -> Any:
    """Create a time entry for a ticket.

    Args:
        ticket_id: The ticket ID
        time_spent: Time spent in hh:mm format (e.g. "01:30")
        agent_id: Agent who spent the time (defaults to current agent)
        billable: Whether the time is billable
        note: Description of work done
        executed_at: When the work was done (ISO 8601)
        timer_running: Start timer immediately
    """
    data: Dict[str, Any] = {"time_spent": time_spent}
    if agent_id:
        data["agent_id"] = agent_id
    if billable is not None:
        data["billable"] = billable
    if note:
        data["note"] = note
    if executed_at:
        data["executed_at"] = executed_at
    if timer_running is not None:
        data["timer_running"] = timer_running
    return await _request("post", f"tickets/{ticket_id}/time_entries", json=data)


@mcp.tool()
async def list_time_entries_for_ticket(ticket_id: int) -> Any:
    """List all time entries for a specific ticket.

    Args:
        ticket_id: The ticket ID
    """
    return await _request("get", f"tickets/{ticket_id}/time_entries")


@mcp.tool()
async def list_all_time_entries() -> Any:
    """List all time entries across all tickets."""
    return await _request("get", "time_entries")


@mcp.tool()
async def update_time_entry(time_entry_id: int, time_entry_fields: Dict[str, Any]) -> Any:
    """Update a time entry.

    Args:
        time_entry_id: The time entry ID
        time_entry_fields: Fields to update (time_spent, note, billable, agent_id, executed_at)
    """
    return await _request("put", f"time_entries/{time_entry_id}", json=time_entry_fields)


@mcp.tool()
async def toggle_timer(time_entry_id: int) -> Any:
    """Start or stop the timer on a time entry.

    Args:
        time_entry_id: The time entry ID
    """
    return await _request("put", f"time_entries/{time_entry_id}/toggle_timer")


@mcp.tool()
async def delete_time_entry(time_entry_id: int) -> Any:
    """Delete a time entry.

    Args:
        time_entry_id: The time entry ID
    """
    return await _request("delete", f"time_entries/{time_entry_id}")


# ===========================================================================
# SATISFACTION RATINGS TOOLS
# ===========================================================================

@mcp.tool()
async def create_satisfaction_rating(ticket_id: int, rating: Dict[str, Any]) -> Any:
    """Create a satisfaction rating for a ticket.

    Args:
        ticket_id: The ticket ID
        rating: Rating data (e.g. {"rating": 103, "feedback": "Great support!"})
    """
    return await _request("post", f"tickets/{ticket_id}/satisfaction_ratings", json=rating)


@mcp.tool()
async def list_satisfaction_ratings_for_ticket(ticket_id: int) -> Any:
    """List all satisfaction ratings for a ticket.

    Args:
        ticket_id: The ticket ID
    """
    return await _request("get", f"tickets/{ticket_id}/satisfaction_ratings")


@mcp.tool()
async def list_all_satisfaction_ratings() -> Any:
    """List all satisfaction ratings across all tickets."""
    return await _request("get", "surveys/satisfaction_ratings")


# ===========================================================================
# CANNED RESPONSE TOOLS
# ===========================================================================

@mcp.tool()
async def list_canned_response_folders() -> Any:
    """List all canned response folders in Freshdesk."""
    return await _request("get", "canned_response_folders")


@mcp.tool()
async def view_canned_response_folder(folder_id: int) -> Any:
    """View a canned response folder.

    Args:
        folder_id: The folder ID
    """
    return await _request("get", f"canned_response_folders/{folder_id}")


@mcp.tool()
async def create_canned_response_folder(name: str) -> Any:
    """Create a canned response folder in Freshdesk.

    Args:
        name: The folder name
    """
    return await _request("post", "canned_response_folders", json={"name": name})


@mcp.tool()
async def update_canned_response_folder(folder_id: int, name: str) -> Any:
    """Update a canned response folder in Freshdesk.

    Args:
        folder_id: The folder ID
        name: The new folder name
    """
    return await _request("put", f"canned_response_folders/{folder_id}", json={"name": name})


@mcp.tool()
async def list_canned_responses(folder_id: int) -> Any:
    """List all canned responses in a folder.

    Args:
        folder_id: The folder ID
    """
    return await _request("get", f"canned_response_folders/{folder_id}/responses")


@mcp.tool()
async def view_canned_response(canned_response_id: int) -> Any:
    """View a canned response in Freshdesk.

    Args:
        canned_response_id: The canned response ID
    """
    return await _request("get", f"canned_responses/{canned_response_id}")


@mcp.tool()
async def create_canned_response(canned_response_fields: Dict[str, Any]) -> Any:
    """Create a canned response in Freshdesk.

    Args:
        canned_response_fields: Response data. Required: title, content_html, folder_id, visibility.
            Optional: group_ids (required if visibility=2)
    """
    try:
        validated = CannedResponseCreate(**canned_response_fields)
        data = validated.model_dump(exclude_none=True)
    except Exception as e:
        return {"error": f"Validation error: {str(e)}"}
    return await _request("post", "canned_responses", json=data)


@mcp.tool()
async def update_canned_response(canned_response_id: int, canned_response_fields: Dict[str, Any]) -> Any:
    """Update a canned response in Freshdesk.

    Args:
        canned_response_id: The canned response ID
        canned_response_fields: Fields to update
    """
    return await _request("put", f"canned_responses/{canned_response_id}", json=canned_response_fields)


@mcp.tool()
async def delete_canned_response(canned_response_id: int) -> Any:
    """Delete a canned response in Freshdesk.

    Args:
        canned_response_id: The canned response ID
    """
    return await _request("delete", f"canned_responses/{canned_response_id}")


# ===========================================================================
# SOLUTION (Knowledge Base) TOOLS
# ===========================================================================

# --- Categories ---

@mcp.tool()
async def list_solution_categories() -> Any:
    """List all solution categories in Freshdesk."""
    return await _request("get", "solutions/categories")


@mcp.tool()
async def view_solution_category(category_id: int) -> Any:
    """View a solution category in Freshdesk.

    Args:
        category_id: The category ID
    """
    return await _request("get", f"solutions/categories/{category_id}")


@mcp.tool()
async def create_solution_category(category_fields: Dict[str, Any]) -> Any:
    """Create a solution category in Freshdesk.

    Args:
        category_fields: Category data. Required: name. Optional: description, visible_in_portals
    """
    if not category_fields.get("name"):
        return {"error": "Name is required"}
    return await _request("post", "solutions/categories", json=category_fields)


@mcp.tool()
async def update_solution_category(category_id: int, category_fields: Dict[str, Any]) -> Any:
    """Update a solution category in Freshdesk.

    Args:
        category_id: The category ID
        category_fields: Fields to update
    """
    return await _request("put", f"solutions/categories/{category_id}", json=category_fields)


@mcp.tool()
async def delete_solution_category(category_id: int) -> Any:
    """Delete a solution category in Freshdesk.

    Args:
        category_id: The category ID
    """
    return await _request("delete", f"solutions/categories/{category_id}")


# --- Folders ---

@mcp.tool()
async def list_solution_folders(category_id: int) -> Any:
    """List all solution folders in a category.

    Args:
        category_id: The category ID
    """
    return await _request("get", f"solutions/categories/{category_id}/folders")


@mcp.tool()
async def view_solution_folder(folder_id: int) -> Any:
    """View a solution folder in Freshdesk.

    Args:
        folder_id: The folder ID
    """
    return await _request("get", f"solutions/folders/{folder_id}")


@mcp.tool()
async def create_solution_folder(category_id: int, folder_fields: Dict[str, Any]) -> Any:
    """Create a solution folder in a category.

    Args:
        category_id: The category ID
        folder_fields: Folder data. Required: name. Optional: description, visibility
    """
    if not folder_fields.get("name"):
        return {"error": "Name is required"}
    return await _request("post", f"solutions/categories/{category_id}/folders", json=folder_fields)


@mcp.tool()
async def update_solution_folder(folder_id: int, folder_fields: Dict[str, Any]) -> Any:
    """Update a solution folder in Freshdesk.

    Args:
        folder_id: The folder ID
        folder_fields: Fields to update
    """
    return await _request("put", f"solutions/folders/{folder_id}", json=folder_fields)


@mcp.tool()
async def delete_solution_folder(folder_id: int) -> Any:
    """Delete a solution folder in Freshdesk.

    Args:
        folder_id: The folder ID
    """
    return await _request("delete", f"solutions/folders/{folder_id}")


@mcp.tool()
async def list_solution_subfolders(folder_id: int) -> Any:
    """List subfolders of a solution folder.

    Args:
        folder_id: The parent folder ID
    """
    return await _request("get", f"solutions/folders/{folder_id}/subfolders")


# --- Articles ---

@mcp.tool()
async def list_solution_articles(folder_id: int) -> Any:
    """List all solution articles in a folder.

    Args:
        folder_id: The folder ID
    """
    return await _request("get", f"solutions/folders/{folder_id}/articles")


@mcp.tool()
async def view_solution_article(article_id: int) -> Any:
    """View a solution article in Freshdesk.

    Args:
        article_id: The article ID
    """
    return await _request("get", f"solutions/articles/{article_id}")


@mcp.tool()
async def create_solution_article(folder_id: int, article_fields: Dict[str, Any]) -> Any:
    """Create a solution article in a folder.

    Args:
        folder_id: The folder ID
        article_fields: Article data. Required: title, description, status (1=draft, 2=published).
            Optional: agent_id, tags, seo_data
    """
    if not article_fields.get("title") or not article_fields.get("status") or not article_fields.get("description"):
        return {"error": "Title, status, and description are required"}
    return await _request("post", f"solutions/folders/{folder_id}/articles", json=article_fields)


@mcp.tool()
async def update_solution_article(article_id: int, article_fields: Dict[str, Any]) -> Any:
    """Update a solution article in Freshdesk.

    Args:
        article_id: The article ID
        article_fields: Fields to update
    """
    return await _request("put", f"solutions/articles/{article_id}", json=article_fields)


@mcp.tool()
async def delete_solution_article(article_id: int) -> Any:
    """Delete a solution article in Freshdesk.

    Args:
        article_id: The article ID
    """
    return await _request("delete", f"solutions/articles/{article_id}")


@mcp.tool()
async def search_solution_articles(term: str) -> Any:
    """Search solution articles by keyword.

    Args:
        term: Search keyword
    """
    return await _request("get", "solutions/articles/search", params={"term": term})


# ===========================================================================
# DISCUSSIONS (Forums) TOOLS
# ===========================================================================

# --- Discussion Categories ---

@mcp.tool()
async def list_discussion_categories() -> Any:
    """List all discussion categories in Freshdesk."""
    return await _request("get", "discussions/categories")


@mcp.tool()
async def view_discussion_category(category_id: int) -> Any:
    """View a discussion category.

    Args:
        category_id: The category ID
    """
    return await _request("get", f"discussions/categories/{category_id}")


@mcp.tool()
async def create_discussion_category(category_fields: Dict[str, Any]) -> Any:
    """Create a discussion category.

    Args:
        category_fields: Category data. Required: name. Optional: description
    """
    return await _request("post", "discussions/categories", json=category_fields)


@mcp.tool()
async def update_discussion_category(category_id: int, category_fields: Dict[str, Any]) -> Any:
    """Update a discussion category.

    Args:
        category_id: The category ID
        category_fields: Fields to update
    """
    return await _request("put", f"discussions/categories/{category_id}", json=category_fields)


@mcp.tool()
async def delete_discussion_category(category_id: int) -> Any:
    """Delete a discussion category.

    Args:
        category_id: The category ID
    """
    return await _request("delete", f"discussions/categories/{category_id}")


# --- Forums ---

@mcp.tool()
async def list_discussion_forums(category_id: int) -> Any:
    """List all forums in a discussion category.

    Args:
        category_id: The category ID
    """
    return await _request("get", f"discussions/categories/{category_id}/forums")


@mcp.tool()
async def view_discussion_forum(forum_id: int) -> Any:
    """View a discussion forum.

    Args:
        forum_id: The forum ID
    """
    return await _request("get", f"discussions/forums/{forum_id}")


@mcp.tool()
async def create_discussion_forum(category_id: int, forum_fields: Dict[str, Any]) -> Any:
    """Create a discussion forum in a category.

    Args:
        category_id: The category ID
        forum_fields: Forum data. Required: name. Optional: description, forum_visibility, forum_type
    """
    return await _request("post", f"discussions/categories/{category_id}/forums", json=forum_fields)


@mcp.tool()
async def update_discussion_forum(forum_id: int, forum_fields: Dict[str, Any]) -> Any:
    """Update a discussion forum.

    Args:
        forum_id: The forum ID
        forum_fields: Fields to update
    """
    return await _request("put", f"discussions/forums/{forum_id}", json=forum_fields)


@mcp.tool()
async def delete_discussion_forum(forum_id: int) -> Any:
    """Delete a discussion forum.

    Args:
        forum_id: The forum ID
    """
    return await _request("delete", f"discussions/forums/{forum_id}")


# --- Topics ---

@mcp.tool()
async def list_discussion_topics(forum_id: int) -> Any:
    """List all topics in a discussion forum.

    Args:
        forum_id: The forum ID
    """
    return await _request("get", f"discussions/forums/{forum_id}/topics")


@mcp.tool()
async def view_discussion_topic(topic_id: int) -> Any:
    """View a discussion topic.

    Args:
        topic_id: The topic ID
    """
    return await _request("get", f"discussions/topics/{topic_id}")


@mcp.tool()
async def create_discussion_topic(forum_id: int, topic_fields: Dict[str, Any]) -> Any:
    """Create a discussion topic in a forum.

    Args:
        forum_id: The forum ID
        topic_fields: Topic data. Required: title, message. Optional: sticky, locked
    """
    return await _request("post", f"discussions/forums/{forum_id}/topics", json=topic_fields)


@mcp.tool()
async def update_discussion_topic(topic_id: int, topic_fields: Dict[str, Any]) -> Any:
    """Update a discussion topic.

    Args:
        topic_id: The topic ID
        topic_fields: Fields to update
    """
    return await _request("put", f"discussions/topics/{topic_id}", json=topic_fields)


@mcp.tool()
async def delete_discussion_topic(topic_id: int) -> Any:
    """Delete a discussion topic.

    Args:
        topic_id: The topic ID
    """
    return await _request("delete", f"discussions/topics/{topic_id}")


# --- Comments ---

@mcp.tool()
async def create_discussion_comment(topic_id: int, body: str) -> Any:
    """Create a comment on a discussion topic.

    Args:
        topic_id: The topic ID
        body: HTML content of the comment
    """
    return await _request("post", f"discussions/topics/{topic_id}/comments", json={"body_html": body})


@mcp.tool()
async def update_discussion_comment(comment_id: int, body: str) -> Any:
    """Update a discussion comment.

    Args:
        comment_id: The comment ID
        body: Updated HTML content
    """
    return await _request("put", f"discussions/comments/{comment_id}", json={"body_html": body})


@mcp.tool()
async def delete_discussion_comment(comment_id: int) -> Any:
    """Delete a discussion comment.

    Args:
        comment_id: The comment ID
    """
    return await _request("delete", f"discussions/comments/{comment_id}")


# ===========================================================================
# ROLES TOOLS
# ===========================================================================

@mcp.tool()
async def list_roles() -> Any:
    """List all roles in Freshdesk."""
    return await _request("get", "roles")


@mcp.tool()
async def view_role(role_id: int) -> Any:
    """View a single role in Freshdesk.

    Args:
        role_id: The role ID
    """
    return await _request("get", f"roles/{role_id}")


# ===========================================================================
# PRODUCTS TOOLS
# ===========================================================================

@mcp.tool()
async def list_products() -> Any:
    """List all products in Freshdesk."""
    return await _request("get", "products")


@mcp.tool()
async def view_product(product_id: int) -> Any:
    """View a single product in Freshdesk.

    Args:
        product_id: The product ID
    """
    return await _request("get", f"products/{product_id}")


@mcp.tool()
async def create_product(product_fields: Dict[str, Any]) -> Any:
    """Create a product in Freshdesk.

    Args:
        product_fields: Product data. Required: name. Optional: description
    """
    return await _request("post", "products", json=product_fields)


@mcp.tool()
async def update_product(product_id: int, product_fields: Dict[str, Any]) -> Any:
    """Update a product in Freshdesk.

    Args:
        product_id: The product ID
        product_fields: Fields to update
    """
    return await _request("put", f"products/{product_id}", json=product_fields)


# ===========================================================================
# EMAIL CONFIGS TOOLS
# ===========================================================================

@mcp.tool()
async def list_email_configs() -> Any:
    """List all email configurations in Freshdesk."""
    return await _request("get", "email_configs")


@mcp.tool()
async def view_email_config(email_config_id: int) -> Any:
    """View a single email configuration.

    Args:
        email_config_id: The email config ID
    """
    return await _request("get", f"email_configs/{email_config_id}")


# ===========================================================================
# SLA POLICIES TOOLS
# ===========================================================================

@mcp.tool()
async def list_sla_policies() -> Any:
    """List all SLA policies in Freshdesk."""
    return await _request("get", "sla_policies")


@mcp.tool()
async def create_sla_policy(policy_fields: Dict[str, Any]) -> Any:
    """Create an SLA policy in Freshdesk.

    Args:
        policy_fields: SLA policy data. Required: name. See API docs for full schema.
    """
    return await _request("post", "sla_policies", json=policy_fields)


@mcp.tool()
async def update_sla_policy(policy_id: int, policy_fields: Dict[str, Any]) -> Any:
    """Update an SLA policy in Freshdesk.

    Args:
        policy_id: The SLA policy ID
        policy_fields: Fields to update
    """
    return await _request("put", f"sla_policies/{policy_id}", json=policy_fields)


# ===========================================================================
# BUSINESS HOURS TOOLS
# ===========================================================================

@mcp.tool()
async def list_business_hours() -> Any:
    """List all business hours configurations in Freshdesk."""
    return await _request("get", "business_hours")


@mcp.tool()
async def view_business_hours(business_hours_id: int) -> Any:
    """View a specific business hours configuration.

    Args:
        business_hours_id: The business hours ID
    """
    return await _request("get", f"business_hours/{business_hours_id}")


# ===========================================================================
# TICKET FORMS TOOLS
# ===========================================================================

@mcp.tool()
async def list_ticket_forms() -> Any:
    """List all ticket forms in Freshdesk."""
    return await _request("get", "ticket-forms")


@mcp.tool()
async def view_ticket_form(form_id: int) -> Any:
    """View a single ticket form.

    Args:
        form_id: The ticket form ID
    """
    return await _request("get", f"ticket-forms/{form_id}")


@mcp.tool()
async def create_ticket_form(form_fields: Dict[str, Any]) -> Any:
    """Create a ticket form in Freshdesk.

    Args:
        form_fields: Ticket form data
    """
    return await _request("post", "ticket-forms", json=form_fields)


@mcp.tool()
async def update_ticket_form(form_id: int, form_fields: Dict[str, Any]) -> Any:
    """Update a ticket form in Freshdesk.

    Args:
        form_id: The ticket form ID
        form_fields: Fields to update
    """
    return await _request("put", f"ticket-forms/{form_id}", json=form_fields)


@mcp.tool()
async def delete_ticket_form(form_id: int) -> Any:
    """Delete a ticket form in Freshdesk.

    Args:
        form_id: The ticket form ID
    """
    return await _request("delete", f"ticket-forms/{form_id}")


# ===========================================================================
# ATTACHMENTS
# ===========================================================================

@mcp.tool()
async def delete_attachment(attachment_id: int) -> Any:
    """Delete an attachment from Freshdesk.

    Args:
        attachment_id: The attachment ID
    """
    return await _request("delete", f"attachments/{attachment_id}")


# ===========================================================================
# PROMPTS
# ===========================================================================

@mcp.prompt()
def create_ticket(
    subject: str,
    description: str,
    source: str,
    priority: str,
    status: str,
    email: str,
) -> str:
    """Create a ticket in Freshdesk"""
    payload = {
        "subject": subject,
        "description": description,
        "source": source,
        "priority": priority,
        "status": status,
        "email": email,
    }
    return f"""
Kindly create a ticket in Freshdesk using the following payload:

{payload}

If you need to retrieve information about any fields (such as allowed values or internal keys), please use the `get_field_properties()` function.

Notes:
- The "type" field is **not** a custom field; it is a standard system field.
- The "type" field is required but should be passed as a top-level parameter, not within custom_fields.
Make sure to reference the correct keys from `get_field_properties()` when constructing the payload.
"""


@mcp.prompt()
def create_reply(
    ticket_id: int,
    reply_message: str,
) -> str:
    """Create a reply in Freshdesk"""
    payload = {
        "body": reply_message,
    }
    return f"""
Kindly create a ticket reply in Freshdesk for ticket ID {ticket_id} using the following payload:

{payload}

Notes:
- The "body" field must be in **HTML format** and should be **brief yet contextually complete**.
- When composing the "body", please **review the previous conversation** in the ticket.
- Ensure the tone and style **match the prior replies**, and that the message provides **full context** so the recipient can understand the issue without needing to re-read earlier messages.
"""


# ===========================================================================
# Main entry point
# ===========================================================================

def main():
    logging.info("Starting Freshdesk MCP server")
    mcp.run(transport='stdio')


if __name__ == "__main__":
    main()
