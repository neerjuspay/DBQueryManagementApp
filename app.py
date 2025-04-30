# START OF QueryManagementApp2_revised_fixed.py
import streamlit as st
import pandas as pd
import datetime
import pymongo
from bson.objectid import ObjectId
import pyperclip
import secrets
import string
import os

from passlib.context import CryptContext # Added for password hashing

# --- Configuration ---

# Set page config (do this first)
st.set_page_config(page_title="Query Management System", layout="wide")

# Initialize password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Database Setup ---

# MongoDB connection using Streamlit Secrets
@st.cache_resource # Cache the connection for efficiency
def get_database():
    """Connects to MongoDB using credentials from st.secrets."""
    try:
        # Access the secrets
        mongo_uri = os.getenv("MONGO_URI")
        client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) # Add timeout
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ping')
        db = client["query_management"] # Use your desired database name
        # st.toast("DB connection successful!", icon="✅") # Optional: uncomment for feedback
        return db
    except pymongo.errors.ConfigurationError as e:
        st.error(f"MongoDB Configuration Error: {e}. Please check your connection string in secrets.toml.", icon="🚨")
        return None
    except pymongo.errors.ConnectionFailure as e:
        st.error(f"MongoDB Connection Failed: {e}. Check network/firewall/DB status or connection string.", icon="🚨")
        return None
    except KeyError:
        st.error("MongoDB URI not found in st.secrets. Please configure .streamlit/secrets.toml", icon="🔒")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during DB connection: {e}", icon="🔥")
        return None

# Initialize collections if they don't exist
def init_db():
    """Initializes DB with default schemas and users if empty."""
    db = get_database()
    # --- FIX: Check using 'is None' ---
    if db is None:
    # --- END FIX ---
        st.error("Database connection failed. Cannot initialize.")
        st.stop() # Stop execution if DB connection fails

    # Hash password function
    def hash_password(password):
        return pwd_context.hash(password)

    # Check if users collection exists and has data
    users_collection = db["users"]
    if users_collection.count_documents({}) == 0:
        st.warning("No users found. Creating default users...")
        default_users = [
            {"email": "dev1@example.com", "name": "Developer 1", "role": "developer", "password": hash_password("password123")},
            {"email": "dev2@example.com", "name": "Developer 2", "role": "developer", "password": hash_password("password123")},
            {"email": "qa1@example.com", "name": "QA 1", "role": "qa", "password": hash_password("password123")},
            {"email": "pm1@example.com", "name": "PM 1", "role": "pm", "password": hash_password("password123")}
        ]
        try:
            users_collection.insert_many(default_users)
            st.success("Default users created.")
        except Exception as e:
            st.error(f"Failed to create default users: {e}")

    # Check if schemas collection exists and has data
    schemas_collection = db["schemas"]
    if schemas_collection.count_documents({}) == 0:
        st.warning("No schemas found. Creating default schemas...")
        default_schemas = [
            {"name": "schema_prod"},
            {"name": "schema_staging"},
            {"name": "schema_test"},
            {"name": "schema_dev"}
        ]
        try:
            schemas_collection.insert_many(default_schemas)
            st.success("Default schemas created.")
        except Exception as e:
            st.error(f"Failed to create default schemas: {e}")

# --- Helper Functions ---

# Verify password hash
def verify_password(plain_password, hashed_password):
    """Verifies a plain password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)

# Hash password
def get_password_hash(password):
    """Hashes a plain password."""
    return pwd_context.hash(password)

# Function to generate query with schema
def generate_schema_query(base_query, schema_name):
    """Replaces schema placeholder in the base query."""
    # Basic check to prevent errors if base_query is None or not a string
    if isinstance(base_query, str):
        return base_query.replace("${SCHEMA}", schema_name)
    return "" # Return empty string or handle as appropriate

# Helper to get combined queries for all schemas
def get_all_schemas_combined_query(base_query, schemas):
    """Generates a single string containing queries for all specified schemas."""
    combined_text = ""
    if not schemas: # Handle empty schema list
        return ""
    for schema in schemas:
        schema_name = schema.get('name', 'UnknownSchema') # Use .get for safety
        generated_query = generate_schema_query(base_query, schema_name)
        combined_text += f"-- Query for {schema_name}\n{generated_query}\n\n"
    return combined_text

# Helper function to generate a secure password
def generate_password(length=12):
    """Generates a random, secure password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    # Ensure length is reasonable
    length = max(8, length) # Minimum length of 8
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

# REFACTORED: Helper to display schema queries and copy buttons
def display_query_schemas_with_copy(query_doc, section_key_prefix):
    """Displays generated queries for each schema with individual and 'Copy All' buttons."""
    st.subheader("Generated Queries")

    # Add "Copy All Schemas" button at the top
    combined_text = get_all_schemas_combined_query(query_doc.get('base_query', ''), query_doc.get('schemas', []))
    if st.button("Copy All Schemas", key=f"copy_all_{section_key_prefix}_{query_doc['_id']}"):
        if combined_text:
             pyperclip.copy(combined_text)
             st.success("All queries copied to clipboard!")
        else:
             st.warning("No queries generated to copy.")


    st.divider() # Use divider for better visual separation

    schemas_list = query_doc.get('schemas', [])
    if not schemas_list:
        st.info("No schemas associated with this query.")
        return

    for i, schema in enumerate(schemas_list):
        schema_name = schema.get('name', f'UnknownSchema_{i}')
        st.markdown(f"#### Query for `{schema_name}`") # Use markdown for emphasis
        generated_query = generate_schema_query(query_doc.get('base_query', ''), schema_name)

        # Display query with copy button
        if generated_query:
            st.code(generated_query, language="sql")
        else:
            st.caption("No query generated for this schema.")

        # Unique key combining prefix, query id, and schema name (safer than index if names repeat)
        copy_key = f"copy_{section_key_prefix}_{query_doc['_id']}_{schema_name}_{i}" # Add index for absolute uniqueness
        if generated_query:
            if st.button("Copy Query", key=copy_key):
                pyperclip.copy(generated_query)
                st.success(f"`{schema_name}` query copied!")

        # Add separator between schemas, but not after the last one
        if i < len(schemas_list) - 1:
            st.divider()

# --- Database Operations ---

# Get current user info
def get_user_info(email):
    """Fetches user document from the database by email."""
    db = get_database()
    # --- FIX: Check using 'is not None' ---
    if db is not None:
    # --- END FIX ---
        try:
            return db["users"].find_one({"email": email})
        except Exception as e:
            st.error(f"Error fetching user info for {email}: {e}")
            return None
    return None

# Get all schemas
def get_all_schemas():
    """Fetches all schema documents from the database."""
    db = get_database()
    # --- FIX: Check using 'is not None' ---
    if db is not None:
    # --- END FIX ---
        try:
            return list(db["schemas"].find())
        except Exception as e:
            st.error(f"Error fetching schemas: {e}")
            return []
    return []

# Create new query
def create_new_query(name, description, base_query, schema_ids, created_by_email):
    """Creates a new query document in the database."""
    db = get_database()
    # --- FIX: Check using 'is None' ---
    if db is None:
    # --- END FIX ---
        st.error("Database connection failed. Cannot create query.")
        return None

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() # Use UTC

    # Prepare schemas mapping
    schemas_list = []
    all_db_schemas_list = get_all_schemas() # Fetch once
    # Convert list to dict for easier lookup
    all_db_schemas = {str(s['_id']): s for s in all_db_schemas_list}

    for schema_id in schema_ids:
        schema_doc = all_db_schemas.get(schema_id)
        if schema_doc:
            schemas_list.append({
                "schema_id": schema_id, # Store as string if needed, or ObjectId
                "name": schema_doc.get("name", "Unnamed Schema"),
                "executed": False,
                "executed_by": None,
                "executed_at": None
            })
        else:
            st.warning(f"Schema ID {schema_id} not found during query creation. Skipping.")


    # Create query document
    query = {
        "name": name,
        "description": description,
        "base_query": base_query,
        "schemas": schemas_list,
        "status": "pending_qa", # Consistent status naming
        "created_by": created_by_email,
        "created_at": timestamp,
        "qa_verified": False,
        "qa_verified_by": None,
        "qa_verified_at": None,
        "pm_approved": False,
        "pm_approved_by": None,
        "pm_approved_at": None,
        "history": [
            {
                "action": "created",
                "by": created_by_email,
                "at": timestamp,
                "note": "Query created"
            }
        ]
    }

    try:
        result = db["queries"].insert_one(query)
        return result.inserted_id
    except Exception as e:
        st.error(f"Failed to insert query into database: {e}")
        return None


# --- Streamlit Sections ---

# User authentication
def login_section():
    """Handles user login."""
    st.sidebar.header("Login")

    with st.sidebar.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Login")

        if login_submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
                return

            db = get_database()
            # --- FIX: Check using 'is None' ---
            if db is None:
            # --- END FIX ---
                st.error("Database connection failed. Cannot log in.")
                return # Stop if DB connection failed

            user = None
            try:
                 user = db["users"].find_one({"email": email})
            except Exception as e:
                 st.error(f"Error during login attempt: {e}")
                 return

            # Use the verify_password helper
            if user and verify_password(password, user.get("password", "")):
                st.session_state.current_user_email = email # Store email in session state
                st.session_state.current_user_name = user.get("name", "Unknown")
                st.session_state.current_user_role = user.get("role", "Unknown")
                st.success(f"Logged in as {st.session_state.current_user_name}")
                st.experimental_rerun() # Rerun to update UI
            else:
                st.error("Invalid email or password")

    # Quick login buttons for demo (Consider removing for production)
    st.sidebar.divider()
    st.sidebar.subheader("Quick Login (Demo)")
    cols = st.sidebar.columns(2)

    def quick_login(email):
        db = get_database()
        # --- FIX: Check using 'is None' ---
        if db is None:
        # --- END FIX ---
             st.error(f"Database connection failed for quick login ({email}).")
             return

        user = None
        try:
            user = db["users"].find_one({"email": email})
        except Exception as e:
            st.error(f"Error during quick login for {email}: {e}")
            return

        if user:
            st.session_state.current_user_email = email
            st.session_state.current_user_name = user.get("name", "Unknown")
            st.session_state.current_user_role = user.get("role", "Unknown")
            st.experimental_rerun()
        else:
            st.error(f"Default user {email} not found.")


    if cols[0].button("Login as Dev"): quick_login("dev1@example.com")
    if cols[1].button("Login as QA"): quick_login("qa1@example.com")
    if cols[0].button("Login as PM"): quick_login("pm1@example.com")
    if cols[1].button("Login as Dev2"): quick_login("dev2@example.com")


# Create new query section for developers
def create_query_section():
    """Section for developers to create new queries."""
    st.header("Create New Query")

    with st.form("create_query_form"):
        query_name = st.text_input("Query Name *")
        query_description = st.text_area("Description")
        base_query = st.text_area("Base Query (Use ${SCHEMA} as placeholder) *", height=200)

        # Get all schemas
        schemas = get_all_schemas() # Already handles DB connection check inside
        if not schemas:
            st.warning("No schemas found in the database. Please add schemas first (or check DB connection).")
            st.form_submit_button("Submit Query", disabled=True) # Disable submit if no schemas
            # Need to return here because schema_options would be empty otherwise
            return

        # Filter out potential None entries if get_all_schemas had issues but didn't return empty
        valid_schemas = [s for s in schemas if s and '_id' in s and 'name' in s]
        if not valid_schemas:
             st.warning("No valid schemas found.")
             st.form_submit_button("Submit Query", disabled=True)
             return

        schema_options = {str(s['_id']): s['name'] for s in valid_schemas}

        # Schema selection
        selected_schemas = st.multiselect("Select Schemas *",
                                         options=list(schema_options.keys()),
                                         format_func=lambda x: schema_options.get(x, f"Invalid ID: {x}"))

        # Submit button
        submitted = st.form_submit_button("Submit Query")

        if submitted:
            # Check current user state exists
            if 'current_user_email' not in st.session_state or not st.session_state.current_user_email:
                 st.error("User session expired or not found. Please log in again.")
                 return

            if query_name and base_query and selected_schemas:
                # Create new query entry
                query_id = create_new_query(
                    query_name,
                    query_description,
                    base_query,
                    selected_schemas,
                    st.session_state.current_user_email # Pass logged-in user's email
                )

                if query_id:
                    st.success(f"Query '{query_name}' submitted successfully! (ID: {query_id})")
                    st.balloons()
                    # Clear form fields potentially? Or just rely on rerun.
                # else: # Error handled and displayed in create_new_query
                    # st.error("Failed to submit query.")
            else:
                st.error("Please fill in all required fields (*)")

    # Preview generated queries (outside the form for better UX)
    if base_query and selected_schemas and schema_options:
        st.divider()
        st.subheader("Preview Generated Queries")
        # Create a dummy query doc structure for the display function
        preview_query_doc = {
            '_id': 'preview', # Dummy ID for key generation
            'base_query': base_query,
            'schemas': [{'name': schema_options.get(sch_id, f"Unknown ID: {sch_id}")} for sch_id in selected_schemas]
        }
        display_query_schemas_with_copy(preview_query_doc, "preview")

# QA verification section
def qa_verification_section():
    """Section for QA to verify queries."""
    st.header("QA Verification Queue")

    db = get_database()
    # --- FIX: Check using 'is None' ---
    if db is None:
    # --- END FIX ---
         st.error("Database connection failed. Cannot load QA queue.")
         return

    pending_queries = []
    try:
        pending_queries = list(db["queries"].find({"status": "pending_qa", "qa_verified": False}))
    except Exception as e:
        st.error(f"Failed to fetch pending QA queries: {e}")
        return

    if not pending_queries:
        st.info("No queries pending QA verification.")
        return

    # Get all user names once for efficiency
    user_emails = list(set(q.get('created_by') for q in pending_queries if q.get('created_by')))
    users_info = {}
    if user_emails:
        try:
            users_info = {u['email']: u.get('name', u['email']) for u in db["users"].find({"email": {"$in": user_emails}})}
        except Exception as e:
            st.warning(f"Could not fetch user details for QA queue: {e}")
            # Continue with emails as fallback names

    for query in pending_queries:
        # Use .get with fallback for safety
        creator_email = query.get("created_by")
        creator_name = users_info.get(creator_email, creator_email if creator_email else "Unknown User")
        query_name = query.get('name', 'Unnamed Query')
        query_id_str = str(query.get('_id', 'no_id'))
        expander_title = f"{query_name} (ID: ...{query_id_str[-6:]}) - By {creator_name}"

        with st.expander(expander_title):
            st.write(f"**Description:** {query.get('description', 'N/A')}")
            st.write(f"**Created at:** {query.get('created_at', 'N/A')}")

            # Use the refactored display function
            display_query_schemas_with_copy(query, "qa")

            st.divider()
            # Check current user state exists
            if 'current_user_email' not in st.session_state or not st.session_state.current_user_email:
                 st.error("User session expired or not found. Please log in again to verify.")
                 continue # Skip verify button for this item if user state lost


            if st.button("Verify Query", key=f"verify_{query_id_str}"):
                timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
                current_user = st.session_state.current_user_email

                update_data = {
                    "$set": {
                        "qa_verified": True,
                        "qa_verified_by": current_user,
                        "qa_verified_at": timestamp,
                        "status": "pending_approval" # Update status
                    },
                    "$push": {
                        "history": {
                            "action": "qa_verified",
                            "by": current_user,
                            "at": timestamp,
                            "note": "Query verified by QA"
                        }
                    }
                }
                try:
                    result = db["queries"].update_one({"_id": query["_id"]}, update_data)
                    if result.modified_count > 0:
                        st.success(f"Query '{query_name}' verified and sent for PM approval!")
                        st.experimental_rerun()
                    else:
                         st.warning("Query verification may not have been saved (no document matched or already verified). Please refresh.")
                except Exception as e:
                    st.error(f"Failed to update query status: {e}")


# PM approval section
def pm_approval_section():
    """Section for PMs to approve verified queries."""
    st.header("PM Approval Queue")

    db = get_database()
    # --- FIX: Check using 'is None' ---
    if db is None:
    # --- END FIX ---
         st.error("Database connection failed. Cannot load PM queue.")
         return

    pending_approval = []
    try:
        # Find queries verified by QA but not yet approved by PM
        pending_approval = list(db["queries"].find(
            {"status": "pending_approval", "qa_verified": True, "pm_approved": False}
        ))
    except Exception as e:
        st.error(f"Failed to fetch pending approval queries: {e}")
        return

    if not pending_approval:
        st.info("No queries pending PM approval.")
        return

    # Get user names
    user_emails = list(set(q.get('created_by') for q in pending_approval if q.get('created_by')))
    qa_emails = list(set(q.get('qa_verified_by') for q in pending_approval if q.get('qa_verified_by')))
    all_involved_emails = list(set(user_emails + qa_emails))
    users_info = {}
    if all_involved_emails:
        try:
            users_info = {u['email']: u.get('name', u['email']) for u in db["users"].find({"email": {"$in": all_involved_emails}})}
        except Exception as e:
            st.warning(f"Could not fetch user details for PM queue: {e}")
            # Continue with emails as fallback names

    for query in pending_approval:
        creator_email = query.get("created_by")
        qa_verifier_email = query.get("qa_verified_by")

        creator_name = users_info.get(creator_email, creator_email if creator_email else "Unknown Creator")
        qa_verifier_name = users_info.get(qa_verifier_email, qa_verifier_email if qa_verifier_email else "N/A")
        query_name = query.get('name', 'Unnamed Query')
        query_id_str = str(query.get('_id', 'no_id'))
        expander_title = f"{query_name} (ID: ...{query_id_str[-6:]}) - By {creator_name}, Verified by {qa_verifier_name}"

        with st.expander(expander_title):
            st.write(f"**Description:** {query.get('description', 'N/A')}")
            st.write(f"**Created at:** {query.get('created_at', 'N/A')}")
            st.write(f"**QA Verified at:** {query.get('qa_verified_at', 'N/A')}")

            # Use the refactored display function
            display_query_schemas_with_copy(query, "pm")

            st.divider()
            # Check current user state exists
            if 'current_user_email' not in st.session_state or not st.session_state.current_user_email:
                 st.error("User session expired or not found. Please log in again to approve.")
                 continue # Skip approve button if user state lost

            if st.button("Approve Query", key=f"approve_{query_id_str}"):
                timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
                current_user = st.session_state.current_user_email

                update_data = {
                    "$set": {
                        "pm_approved": True,
                        "pm_approved_by": current_user,
                        "pm_approved_at": timestamp,
                        "status": "approved" # Final approved status
                    },
                    "$push": {
                        "history": {
                            "action": "pm_approved",
                            "by": current_user,
                            "at": timestamp,
                            "note": "Query approved by PM"
                        }
                    }
                }
                try:
                    result = db["queries"].update_one({"_id": query["_id"]}, update_data)
                    if result.modified_count > 0:
                        st.success(f"Query '{query_name}' approved!")
                        st.experimental_rerun()
                    else:
                        st.warning("Query approval may not have been saved (no document matched or already approved). Please refresh.")
                except Exception as e:
                    st.error(f"Failed to update query status: {e}")


# Execution section for QA and developers
def execution_section():
    """Section for Dev/QA to mark queries as executed."""
    st.header("Execute Approved Queries")

    db = get_database()
    # --- FIX: Check using 'is None' ---
    if db is None:
    # --- END FIX ---
         st.error("Database connection failed. Cannot load execution queue.")
         return

    approved_queries = []
    try:
        # Find queries approved by PM
        approved_queries = list(db["queries"].find(
            {"status": "approved", "pm_approved": True}
        ).sort("created_at", -1)) # Sort by newest first
    except Exception as e:
        st.error(f"Failed to fetch approved queries: {e}")
        return

    if not approved_queries:
        st.info("No approved queries available for execution.")
        return

    # Get user names involved in these queries
    user_emails = set()
    for q in approved_queries:
        user_emails.add(q.get('created_by'))
        user_emails.add(q.get('pm_approved_by'))
        for s in q.get('schemas', []):
            user_emails.add(s.get('executed_by'))
    # Remove None if present
    user_emails.discard(None)

    users_info = {}
    if user_emails:
         try:
             users_info = {u['email']: u.get('name', u['email']) for u in db["users"].find({"email": {"$in": list(user_emails)}})}
         except Exception as e:
             st.warning(f"Could not fetch user details for execution queue: {e}")


    for query in approved_queries:
        creator_email = query.get("created_by")
        pm_approver_email = query.get("pm_approved_by")

        creator_name = users_info.get(creator_email, creator_email if creator_email else "Unknown Creator")
        pm_approver_name = users_info.get(pm_approver_email, pm_approver_email if pm_approver_email else "N/A")
        query_name = query.get('name', 'Unnamed Query')
        query_id_str = str(query.get('_id', 'no_id'))
        expander_title = f"{query_name} (ID: ...{query_id_str[-6:]}) - By {creator_name}, Approved by {pm_approver_name}"

        with st.expander(expander_title):
            st.write(f"**Description:** {query.get('description', 'N/A')}")
            st.write(f"**Approved at:** {query.get('pm_approved_at', 'N/A')}")

            st.subheader("Queries & Execution Status")
            st.caption("Copy the query below and run it in your environment. Mark as executed once done.")

            # Add "Copy All Schemas" button at the top
            combined_text = get_all_schemas_combined_query(query.get('base_query', ''), query.get('schemas', []))
            if st.button("Copy All Queries", key=f"copy_all_exec_{query_id_str}"):
                 if combined_text:
                     pyperclip.copy(combined_text)
                     st.success("All queries copied to clipboard!")
                 else:
                     st.warning("No queries generated to copy.")

            st.divider()

            schemas_list = query.get('schemas', [])
            if not schemas_list:
                 st.info("No schemas associated with this query.")
                 continue # Skip to next query if no schemas

            for i, schema in enumerate(schemas_list):
                schema_name = schema.get('name', f'UnknownSchema_{i}')
                st.markdown(f"#### Query for `{schema_name}`")
                generated_query = generate_schema_query(query.get('base_query', ''), schema_name)

                # Display query with copy button
                if generated_query:
                    st.code(generated_query, language="sql")
                else:
                    st.caption("No query generated for this schema.")

                # Check current user state exists before showing buttons
                if 'current_user_email' not in st.session_state or not st.session_state.current_user_email:
                    st.warning("User session expired or not found. Please log in again to execute/copy.")
                    continue # Skip buttons for this schema if user state lost


                cols = st.columns([1, 3])
                with cols[0]:
                    # Copy button
                    copy_key = f"copy_exec_{query_id_str}_{schema_name}_{i}"
                    if generated_query:
                        if st.button("Copy", key=copy_key):
                            pyperclip.copy(generated_query)
                            st.success("Copied!")

                with cols[1]:
                    # Execution status and button
                    executed = schema.get('executed', False)
                    if executed:
                        executor_email = schema.get('executed_by')
                        executor_name = users_info.get(executor_email, executor_email if executor_email else "Unknown Executor")
                        executed_at = schema.get('executed_at', 'N/A')
                        st.success(f"Executed by {executor_name} at {executed_at}")
                    else:
                        exec_key = f"exec_{query_id_str}_{schema_name}_{i}"
                        if st.button(f"Mark as Executed", key=exec_key):
                            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
                            current_user = st.session_state.current_user_email

                            # Update execution status for this specific schema in the array
                            try:
                                result = db["queries"].update_one(
                                    # Match the main document AND the specific element in the schemas array
                                    {"_id": query["_id"], "schemas.name": schema_name},
                                    {
                                        "$set": {
                                            # Use positional '$' operator to update the matched element
                                            "schemas.$.executed": True,
                                            "schemas.$.executed_by": current_user,
                                            "schemas.$.executed_at": timestamp
                                        },
                                        "$push": {
                                            "history": {
                                                "action": "executed",
                                                "schema": schema_name,
                                                "by": current_user,
                                                "at": timestamp,
                                                "note": f"Query marked as executed on schema '{schema_name}'"
                                            }
                                        }
                                    }
                                )
                                if result.modified_count > 0:
                                     st.success(f"Query marked as executed on {schema_name}!")
                                     st.experimental_rerun()
                                else:
                                     # This might happen if the schema name wasn't found or update failed silently
                                     st.warning(f"Could not mark query as executed for schema '{schema_name}'. The schema name might be incorrect or the query state changed. Please refresh.")

                            except Exception as e:
                                st.error(f"Failed to update execution status: {e}")

                # Add separator between schemas
                if i < len(schemas_list) - 1:
                    st.divider()


# Helper function to generate grants based on role (Keep specific to DB type if needed)
def generate_grants_for_role(role, username):
    """Generates placeholder SQL GRANT statements based on role."""
    st.caption("Note: These GRANT statements are examples (MySQL syntax). Adjust for your specific database.")
    # Basic input sanitation
    safe_username = username.replace("'", "''") # Basic protection against SQL injection in username if manually edited
    if role == "developer":
        # Developers might need more permissions on specific schemas/tables in real scenarios
        return f"GRANT SELECT, INSERT, UPDATE, DELETE ON *.* TO '{safe_username}';" # Example, likely too broad
    elif role == "qa":
        return f"GRANT SELECT ON *.* TO '{safe_username}';" # Example
    elif role == "pm":
        # PMs might need user admin privileges in some systems, or just SELECT
        return f"""GRANT SELECT ON *.* TO '{safe_username}';
-- Example if PM manages DB users: GRANT CREATE USER ON *.* TO '{safe_username}' WITH GRANT OPTION;"""
    else:
        return f"-- Default: Grant SELECT privilege\nGRANT SELECT ON *.* TO '{safe_username}';"

# User management section for admins (PM role)
def user_management_section():
    """Section for PMs to manage users and generate DB credentials."""
    st.header("User Management")

    db = get_database()
    # --- FIX: Check using 'is None' ---
    if db is None:
    # --- END FIX ---
         st.error("Database connection failed. Cannot manage users.")
         return

    # --- Display Users ---
    st.subheader("Current Users")
    all_users = []
    try:
        # Sort by name for consistency
        all_users = list(db["users"].find().sort("name", 1))
    except Exception as e:
        st.error(f"Failed to fetch users: {e}")
        # all_users remains empty

    if not all_users:
        st.info("No users found in the database.")
    else:
        users_data = []
        for user in all_users:
            users_data.append({
                "Name": user.get("name", "N/A"),
                "Email": user.get("email", "N/A"),
                "Role": user.get("role", "N/A").upper(),
                "Created At": user.get("created_at", "N/A")
            })
        # Use email as index if unique, otherwise default index
        try:
             df = pd.DataFrame(users_data).set_index("Email")
        except: # Fallback if emails are not unique (shouldn't happen with checks)
             df = pd.DataFrame(users_data)
        st.dataframe(df, use_container_width=True)

    st.divider()

    # --- Create New User ---
    st.subheader("Create New User")
    # Use session state to store generated password temporarily for display
    if 'generated_password_info' not in st.session_state:
        st.session_state.generated_password_info = None # Store dict {email: pw}

    with st.form("create_new_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_email = st.text_input("Email *").strip()
            new_name = st.text_input("Full Name *").strip()
        with col2:
            role_options = ["developer", "qa", "pm"]
            new_role = st.selectbox("Role *", role_options)
            password_option = st.radio("Password Option", ["Generate Secure Password", "Enter Password"], key="pw_option")

        if password_option == "Enter Password":
            new_password_plain = st.text_input("Password *", type="password")
        else:
            # Generate within the form submission logic if chosen
            new_password_plain = None # Placeholder

        submitted = st.form_submit_button("Create User")

        if submitted:
             # Check current user state exists
            if 'current_user_email' not in st.session_state or not st.session_state.current_user_email:
                 st.error("User session expired or not found. Please log in again to create users.")
                 # Clear potentially stored password if form submitted without session
                 st.session_state.generated_password_info = None
                 return # Stop processing

            final_password_plain = None
            if password_option == "Enter Password":
                final_password_plain = new_password_plain
            else: # Generate password
                final_password_plain = generate_password()
                # Store temporarily for display after rerun
                st.session_state.generated_password_info = {"email": new_email, "password": final_password_plain}


            # Basic validation
            if not new_email or not new_name or not new_role or not final_password_plain:
                st.error("Please fill in all required fields (*).")
                st.session_state.generated_password_info = None # Clear generated pw info if error
            elif "@" not in new_email or "." not in new_email.split('@')[-1]: # Basic email format check
                 st.error("Please enter a valid email address.")
                 st.session_state.generated_password_info = None # Clear generated pw info if error
            else:
                user_exists = False
                try:
                    # Check if user already exists
                    if db["users"].find_one({"email": new_email}):
                        user_exists = True
                except Exception as e:
                    st.error(f"Database error checking for existing user: {e}")
                    st.session_state.generated_password_info = None
                    return # Don't proceed if DB check failed

                if user_exists:
                    st.error("User with this email already exists.")
                    st.session_state.generated_password_info = None # Clear generated pw info if error
                else:
                    # Hash the password before storing
                    hashed_password = get_password_hash(final_password_plain)

                    user_data = {
                        "email": new_email,
                        "name": new_name,
                        "role": new_role,
                        "password": hashed_password, # Store the hash
                        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "created_by": st.session_state.current_user_email
                    }

                    try:
                        db["users"].insert_one(user_data)
                        st.success(f"User '{new_name}' ({new_email}) created successfully!")
                        # Don't display password here directly, use session state after rerun
                        st.experimental_rerun() # Rerun to update user list and display password info
                    except Exception as e:
                        st.error(f"Failed to create user in database: {e}")
                        st.session_state.generated_password_info = None # Clear generated pw info if error


    # Display generated password AFTER successful creation (triggered by rerun)
    if st.session_state.get("generated_password_info"):
        info = st.session_state.generated_password_info
        st.info(f"Generated password for {info['email']}: `{info['password']}`")
        if st.button("Copy Generated Password"):
            pyperclip.copy(info['password'])
            st.success("Password copied to clipboard!")
        # Clear the state variable after displaying
        st.session_state.generated_password_info = None


    st.divider()

    # --- Generate SQL Create User Statements ---
    st.subheader("Generate DB User Creation SQL")
    st.caption("Generates SQL for creating a corresponding database user (optional).")

    if all_users: # Only show if there are users to select
        # Use Name (Email) for better readability in dropdown
        user_options = {u["email"]: f"{u.get('name', 'N/A')} ({u['email']})" for u in all_users}
        selected_user_email = st.selectbox(
            "Select a user to generate DB user SQL",
            options=list(user_options.keys()),
            format_func=lambda x: user_options.get(x, x),
            index=0 # Default to first user
            )

        if selected_user_email:
             # Find the selected user details again (all_users might be stale if creation just happened)
             selected_user_details = None
             try:
                selected_user_details = db["users"].find_one({"email": selected_user_email})
             except Exception as e:
                 st.error(f"Could not fetch details for selected user {selected_user_email}: {e}")

             if selected_user_details:
                # Generate a suggested DB username (e.g., 'jdoe' from 'jdoe@example.com')
                db_username_suggestion = selected_user_email.split("@")[0].replace(".", "_").replace("-","_") # Basic suggestion
                db_username = st.text_input("Database Username", value=db_username_suggestion)

                # Generate a new secure password for the DB user each time this section is viewed
                # Avoid storing DB passwords directly in the app's user document if possible
                db_password = generate_password(16)

                # Generate CREATE USER SQL statement
                if db_username: # Only proceed if username is not empty
                    sql_stmt = f"""-- SQL statement to create database user '{db_username}'
-- Ensure this syntax matches your specific database (e.g., MySQL, PostgreSQL)

-- Example for MySQL:
CREATE USER '{db_username}'@'%' IDENTIFIED BY '{db_password}';
-- For PostgreSQL: CREATE USER "{db_username}" WITH PASSWORD '{db_password}'; -- Double quotes might be needed

-- Grant privileges based on role (adjust grants as needed for your DB and security policies)
{generate_grants_for_role(selected_user_details.get("role",""), db_username)}

-- Example for MySQL: Flush privileges to apply changes if needed
-- FLUSH PRIVILEGES;
"""
                    st.code(sql_stmt, language="sql")
                    if st.button("Copy SQL Statement"):
                        pyperclip.copy(sql_stmt)
                        st.success("SQL copied to clipboard!")
                else:
                    st.warning("Please provide a database username.")
             else:
                st.warning("Selected user details not found (may have been deleted or DB error).")
    else:
        st.info("Create users before generating SQL.")


# Query history section
def query_history_section():
    """Displays a filterable history of all queries."""
    st.header("Query History")

    db = get_database()
    # --- FIX: Check using 'is None' ---
    if db is None:
    # --- END FIX ---
         st.error("Database connection failed. Cannot load query history.")
         return

    all_queries = []
    try:
        all_queries = list(db["queries"].find().sort("created_at", -1))
    except Exception as e:
        st.error(f"Failed to fetch query history: {e}")
        return # Don't proceed if fetching failed

    if not all_queries:
        st.info("No query history found.")
        return

    # --- Prepare Data & Filters ---
    # Fetch all users involved in history for efficient lookup
    user_emails = set()
    for q in all_queries:
        user_emails.add(q.get('created_by'))
        user_emails.add(q.get('qa_verified_by'))
        user_emails.add(q.get('pm_approved_by'))
        for h in q.get('history', []):
            user_emails.add(h.get('by'))
        for s in q.get('schemas', []):
            user_emails.add(s.get('executed_by'))
    # Remove None if present
    user_emails.discard(None)

    users_info = {}
    if user_emails:
         try:
             users_info = {u['email']: u.get('name', u['email']) for u in db["users"].find({"email": {"$in": list(user_emails)}})}
         except Exception as e:
             st.warning(f"Could not fetch user details for history view: {e}")


    queries_data = []
    all_creators = set()
    all_statuses = set()

    for q in all_queries:
        creator_email = q.get("created_by")
        creator_name = users_info.get(creator_email, creator_email if creator_email else "Unknown") # Fallback to email
        all_creators.add(creator_name)

        status = q.get("status", "unknown")
        status_display = status.replace("_", " ").title()
        all_statuses.add(status_display)

        schema_names = [s.get('name', 'N/A') for s in q.get('schemas', [])]

        # More informative status icons
        qa_status = "❓" # Default/Unknown
        if status == "pending_qa": qa_status = "⏳"
        elif q.get("qa_verified"): qa_status = "✅"
        elif status in ["pending_approval", "approved"]: qa_status = "❌" # Implies skipped or issue if not verified but later status

        pm_status = "❓" # Default/Unknown
        if status == "pending_approval": pm_status = "⏳"
        elif q.get("pm_approved"): pm_status = "✅"
        elif status == "approved": pm_status = "❌" # Implies skipped or issue if not approved but status is approved

        queries_data.append({
            "ID": f"...{str(q.get('_id', 'no_id'))[-6:]}", # Short ID for display
            "Name": q.get("name", "Unnamed Query"),
            "Status": status_display,
            "Created By": creator_name,
            "Created At": q.get("created_at", "N/A"),
            "QA": qa_status,
            "PM": pm_status,
            "Schemas": ", ".join(schema_names) if schema_names else "N/A",
            "full_id": str(q.get("_id")) # Keep full ID for lookup
        })

    df = pd.DataFrame(queries_data)

    # Filters
    st.subheader("Filters")
    col1, col2 = st.columns(2)
    with col1:
        # Provide default=[] for multiselect
        status_filter = st.multiselect("Filter by Status", options=sorted(list(all_statuses)), default=[])
    with col2:
        creator_filter = st.multiselect("Filter by Creator", options=sorted(list(all_creators)), default=[])

    # Apply filters
    filtered_df = df.copy()
    if status_filter:
        filtered_df = filtered_df[filtered_df["Status"].isin(status_filter)]
    if creator_filter:
        filtered_df = filtered_df[filtered_df["Created By"].isin(creator_filter)]

    # --- Display Table ---
    st.subheader("Query List")
    if not filtered_df.empty:
        st.dataframe(filtered_df.drop(columns=["full_id"]), use_container_width=True)
    else:
        st.info("No queries match the current filters.")


    st.divider()

    # --- Query Details ---
    st.subheader("View Query Details")
    if not filtered_df.empty:
        # Create mapping from display name+ID back to full_id for unique selection
        query_options_map = { f"{row['Name']} ({row['ID']})" : row['full_id'] for index, row in filtered_df.iterrows()}
        # Add a default "Select..." option
        options_list = ["Select a query..."] + list(query_options_map.keys())
        selected_query_display = st.selectbox("Select a query from the filtered list above",
                                             options=options_list, index=0) # Default to "Select..."

        if selected_query_display != "Select a query...":
            query_id = query_options_map[selected_query_display]
            # Find the original query document from the initial list more safely
            query_data = next((q for q in all_queries if str(q.get('_id')) == query_id), None)

            if query_data:
                creator_email = query_data.get("created_by")
                qa_verifier_email = query_data.get("qa_verified_by")
                pm_approver_email = query_data.get("pm_approved_by")

                creator_name = users_info.get(creator_email, creator_email if creator_email else "Unknown")
                qa_verifier_name = users_info.get(qa_verifier_email, qa_verifier_email if qa_verifier_email else "N/A")
                pm_approver_name = users_info.get(pm_approver_email, pm_approver_email if pm_approver_email else "N/A")

                tab1, tab2, tab3 = st.tabs(["📋 Details", "📜 Schemas & Queries", "⏳ History Log"])

                with tab1:
                    st.markdown(f"**Name:** {query_data.get('name', 'N/A')}")
                    st.markdown(f"**Description:** {query_data.get('description', 'N/A')}")
                    st.markdown(f"**Status:** {query_data.get('status', 'N/A').replace('_', ' ').title()}")
                    st.markdown(f"**Created by:** {creator_name}")
                    st.markdown(f"**Created at:** {query_data.get('created_at', 'N/A')}")
                    st.markdown(f"**QA Verified:** {'Yes by ' + qa_verifier_name if query_data.get('qa_verified') else 'No'}")
                    st.markdown(f"**QA Verified at:** {query_data.get('qa_verified_at', 'N/A')}")
                    st.markdown(f"**PM Approved:** {'Yes by ' + pm_approver_name if query_data.get('pm_approved') else 'No'}")
                    st.markdown(f"**PM Approved at:** {query_data.get('pm_approved_at', 'N/A')}")

                with tab2:
                    # Use the refactored display function
                    display_query_schemas_with_copy(query_data, "hist")

                    st.divider()
                    st.subheader("Execution Status Summary")
                    schemas_list = query_data.get('schemas', [])
                    if schemas_list:
                        for schema in schemas_list:
                            schema_name = schema.get('name', 'Unknown Schema')
                            st.markdown(f"**`{schema_name}`:**")
                            if schema.get('executed', False):
                                executor_email = schema.get('executed_by')
                                executor_name = users_info.get(executor_email, executor_email if executor_email else "Unknown")
                                st.success(f"Executed by {executor_name} at {schema.get('executed_at', 'N/A')}")
                            else:
                                st.warning("Not yet executed")
                    else:
                        st.info("No schemas associated with this query.")

                with tab3:
                    st.subheader("Activity Log")
                    history_log = query_data.get("history", [])
                    if history_log:
                        history_data = []
                        # Sort by timestamp string - might not be perfect if formats vary, but ISO format should sort ok
                        for event in sorted(history_log, key=lambda x: x.get('at', '')):
                            actor_email = event.get("by")
                            user_name = users_info.get(actor_email, actor_email if actor_email else "System/Unknown")

                            history_data.append({
                                "Timestamp": event.get("at", "N/A"),
                                "Action": event.get("action", "unknown").replace("_", " ").title(),
                                "Performed By": user_name,
                                "Schema": event.get("schema", "-"), # Display schema if available
                                "Note": event.get("note", "-")
                            })

                        history_df = pd.DataFrame(history_data)
                        st.dataframe(history_df, use_container_width=True)
                    else:
                        st.info("No history log available for this query.")
            else:
                st.error("Selected query data could not be loaded. It might have been deleted.")
        # else: # No query selected from dropdown
            # st.info("Select a query from the dropdown above to see details.")

    # else: # Filtered DF is empty
        # Handled by the "No queries match..." message after the dataframe display

# --- Main App Logic ---
def main():
    """Main function to run the Streamlit application."""
    st.title("🚀 Query Management System")

    # Initialize database (creates defaults if needed)
    # Errors during init/connection are handled within get_database/init_db
    init_db() # This function now calls st.stop() if DB connection fails


    # Initialize session state for user login
    if 'current_user_email' not in st.session_state:
        st.session_state.current_user_email = None
    if 'current_user_name' not in st.session_state:
        st.session_state.current_user_name = None
    if 'current_user_role' not in st.session_state:
        st.session_state.current_user_role = None


    # --- Login Check ---
    if st.session_state.current_user_email is None:
        login_section()
        st.warning("Please log in using the sidebar to access the system.")
        st.stop() # Stop execution if not logged in

    # --- Logged-in User View ---
    # Retrieve from session state (should be set if past the login check)
    user_role = st.session_state.get("current_user_role", "Unknown")
    user_name = st.session_state.get("current_user_name", "Unknown")

    # Display logged-in user info in sidebar
    st.sidebar.success(f"Logged in as {user_name} ({user_role.upper()})")
    if st.sidebar.button("Logout"):
        # Clear all session state related to user and generated passwords etc.
        keys_to_delete = [k for k in st.session_state.keys()] # Get all keys
        for key in keys_to_delete:
            del st.session_state[key]
        # st.session_state.clear() # Alternatively, clear everything
        st.success("Logged out successfully.")
        st.experimental_rerun()

    st.sidebar.divider()
    st.sidebar.header("Navigation")

    # --- Role-Based Navigation ---
    # Define pages accessible by each role
    role_pages = {
        "developer": ["Query History", "Create Query", "Execute Queries"],
        "qa": ["Query History", "QA Verification", "Execute Queries"],
        "pm": ["Query History", "Create Query", "QA Verification", "PM Approval", "Execute Queries", "User Management"]
    }

    # Get available pages for the current user's role, default to Query History only
    available_pages = role_pages.get(user_role, ["Query History"])

    # Define a preferred order
    page_order = ["Query History", "Create Query", "QA Verification", "PM Approval", "Execute Queries", "User Management"]
    # Filter available pages based on the preferred order
    ordered_available_pages = [p for p in page_order if p in available_pages]

    # Use radio buttons for navigation
    # Check if ordered_available_pages is not empty before creating radio
    if ordered_available_pages:
         page = st.sidebar.radio("Go to", ordered_available_pages)
    else:
         # Fallback if something went wrong with role/page definition
         st.sidebar.warning("No navigation options available for your role.")
         page = "Query History" # Default to history

    st.sidebar.divider()

    # --- Page Rendering ---
    # Use a dictionary or if/elif structure for cleaner page routing
    page_render_functions = {
        "Query History": query_history_section,
        "Create Query": create_query_section,
        "QA Verification": qa_verification_section,
        "PM Approval": pm_approval_section,
        "Execute Queries": execution_section,
        "User Management": user_management_section
    }

    # Check if the selected page is valid for the user's role before rendering
    if page in available_pages:
        render_func = page_render_functions.get(page)
        if render_func:
            render_func() # Call the function to render the page
        else:
            st.error(f"Error: Page '{page}' function not defined.")
    else:
        # This case should ideally not be reached due to filtered radio options
        st.error(f"Access Denied: You do not have permission to view the '{page}' section.")
        query_history_section() # Show history as a safe default


if __name__ == "__main__":
    main()

# END OF QueryManagementApp2_revised_fixed.py
