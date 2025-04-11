import streamlit as st
import requests
import json
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import time

# API URL
API_URL = "http://localhost:8000/api"

st.set_page_config(
    page_title="Serverless Function Platform",
    page_icon="⚡",
    layout="wide"
)

# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Functions", "Metrics", "System Stats"])

# Helper functions
def get_functions():
    response = requests.get(f"{API_URL}/functions/")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error fetching functions: {response.text}")
        return []

def get_function(function_id):
    response = requests.get(f"{API_URL}/functions/{function_id}")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error fetching function: {response.text}")
        return None

def create_function(name, route, language, code, timeout, memory):
    data = {
        "name": name,
        "route": route,
        "language": language,
        "code": code,
        "timeout": timeout,
        "memory": memory
    }
    response = requests.post(f"{API_URL}/functions/", json=data)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error creating function: {response.text}")
        return None

def update_function(function_id, name=None, route=None, language=None, code=None, timeout=None, memory=None):
    data = {}
    if name:
        data["name"] = name
    if route:
        data["route"] = route
    if language:
        data["language"] = language
    if code:
        data["code"] = code
    if timeout:
        data["timeout"] = timeout
    if memory:
        data["memory"] = memory
    
    response = requests.put(f"{API_URL}/functions/{function_id}", json=data)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error updating function: {response.text}")
        return None

def delete_function(function_id):
    response = requests.delete(f"{API_URL}/functions/{function_id}")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error deleting function: {response.text}")
        return None

def invoke_function(function_id, parameters, virtualization):
    data = {"parameters": parameters}
    response = requests.post(f"{API_URL}/functions/{function_id}/invoke?virtualization={virtualization}", json=data)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error invoking function: {response.text}")
        return None

def get_function_metrics(function_id):
    response = requests.get(f"{API_URL}/metrics/functions/{function_id}")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error fetching metrics: {response.text}")
        return []

def get_function_executions(function_id):
    response = requests.get(f"{API_URL}/functions/{function_id}/executions")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error fetching executions: {response.text}")
        return []

def compare_virtualization():
    response = requests.get(f"{API_URL}/metrics/compare")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error comparing virtualization: {response.text}")
        return {}

# Functions page
if page == "Functions":
    st.title("Functions")
    
    # Create new function
    with st.expander("Create New Function"):
        with st.form("create_function"):
            name = st.text_input("Function Name")
            route = st.text_input("Route (e.g., /hello)")
            language = st.selectbox("Language", ["python", "javascript"])
            
            # Default code based on language
            if language == "python":
                default_code = """def handler(event):
    # Your code here
    name = event.get('name', 'World')
    return {
        'message': f'Hello, {name}!'
    }
"""
            else:
                default_code = """exports.handler = async (event) => {
    // Your code here
    const name = event.name || 'World';
    return {
        message: `Hello, ${name}!`
    };
};
"""
            
            code = st.text_area("Code", value=default_code, height=300)
            timeout = st.number_input("Timeout (seconds)", min_value=1, max_value=300, value=30)
            memory = st.number_input("Memory (MB)", min_value=64, max_value=1024, value=128)
            
            submit = st.form_submit_button("Create Function")
            
            if submit:
                if not name or not route:
                    st.error("Name and route are required")
                else:
                    if not route.startswith("/"):
                        route = f"/{route}"
                    
                    result = create_function(name, route, language, code, timeout, memory)
                    if result:
                        st.success(f"Function '{name}' created successfully!")
    
    # List functions
    st.subheader("Your Functions")
    functions = get_functions()
    
    if not functions:
        st.info("No functions found. Create one above!")
    else:
        for function in functions:
            with st.expander(f"{function['name']} ({function['route']})"):
                tabs = st.tabs(["Details", "Code", "Test", "Executions"])
                
                with tabs[0]:
                    st.write(f"**ID:** {function['id']}")
                    st.write(f"**Language:** {function['language']}")
                    st.write(f"**Timeout:** {function['timeout']} seconds")
                    st.write(f"**Memory:** {function['memory']} MB")
                    st.write(f"**Created:** {function['created_at']}")
                    st.write(f"**Updated:** {function['updated_at']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"Delete {function['name']}", key=f"delete_{function['id']}"):
                            if delete_function(function['id']):
                                st.success(f"Function '{function['name']}' deleted successfully!")
                                st.rerun()
                
                with tabs[1]:
                    updated_code = st.text_area(
                        "Function Code", 
                        value=function['code'], 
                        height=300,
                        key=f"code_{function['id']}"
                    )
                    
                    if st.button("Update Code", key=f"update_code_{function['id']}"):
                        if update_function(function['id'], code=updated_code):
                            st.success("Code updated successfully!")
                
                with tabs[2]:
                    st.subheader("Test Function")
                    
                    # Input parameters
                    params_str = st.text_area(
                        "Input Parameters (JSON)", 
                        value="{\n  \"name\": \"User\"\n}",
                        height=150,
                        key=f"params_{function['id']}"
                    )
                    
                    # Parse parameters
                    try:
                        params = json.loads(params_str)
                    except json.JSONDecodeError:
                        st.error("Invalid JSON")
                        params = {}
                    
                    # Select virtualization
                    virtualization = st.radio(
                        "Virtualization", 
                        ["docker", "gvisor"],
                        key=f"virt_{function['id']}"
                    )
                    
                    # Invoke function
                    if st.button("Invoke", key=f"invoke_{function['id']}"):
                        with st.spinner("Invoking function..."):
                            start_time = time.time()
                            result = invoke_function(function['id'], params, virtualization)
                            end_time = time.time()
                            
                            if result:
                                st.success(f"Function executed in {result['duration']:.2f} ms")
                                st.json(result['result'])
                
                with tabs[3]:
                    st.subheader("Execution History")
                    executions = get_function_executions(function['id'])
                    
                    if not executions:
                        st.info("No executions found")
                    else:
                        # Convert to DataFrame
                        df = pd.DataFrame(executions)
                        df['start_time'] = pd.to_datetime(df['start_time'])
                        df['end_time'] = pd.to_datetime(df['end_time'])
                        df = df.sort_values('start_time', ascending=False)
                        
                        # Display as table
                        st.dataframe(
                            df[['id', 'start_time', 'status', 'virtualization', 'duration', 'memory_used', 'cpu_used']],
                            use_container_width=True
                        )

# Metrics page
elif page == "Metrics":
    st.title("Function Metrics")
    
    # Get all functions
    functions = get_functions()
    
    if not functions:
        st.info("No functions found")
    else:
        # Select function
        function_names = {f['id']: f['name'] for f in functions}
        selected_function_id = st.selectbox(
            "Select Function",
            options=list(function_names.keys()),
            format_func=lambda x: function_names[x]
        )
        
        # Get metrics for selected function
        metrics = get_function_metrics(selected_function_id)
        
        if not metrics:
            st.info("No metrics found for this function")
        else:
            # Display metrics
            st.subheader("Performance Metrics")
            
            # Group by virtualization
            docker_metrics = next((m for m in metrics if m["virtualization"] == "docker"), None)
            gvisor_metrics = next((m for m in metrics if m["virtualization"] == "gvisor"), None)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Docker")
                if docker_metrics:
                    st.metric("Avg. Duration", f"{docker_metrics['avg_duration_ms']:.2f} ms")
                    st.metric("Avg. Memory Used", f"{docker_metrics['avg_memory_used_mb']:.2f} MB")
                    st.metric("Total Executions", docker_metrics['total_executions'])
                    st.metric("Success Rate", f"{docker_metrics['success_rate'] * 100:.1f}%")
                    st.metric("Warm Starts", docker_metrics['warm_starts'])
                    st.metric("Cold Starts", docker_metrics['cold_starts'])
                else:
                    st.info("No Docker metrics available")
            
            with col2:
                st.subheader("gVisor")
                if gvisor_metrics:
                    st.metric("Avg. Duration", f"{gvisor_metrics['avg_duration_ms']:.2f} ms")
                    st.metric("Avg. Memory Used", f"{gvisor_metrics['avg_memory_used_mb']:.2f} MB")
                    st.metric("Total Executions", gvisor_metrics['total_executions'])
                    st.metric("Success Rate", f"{gvisor_metrics['success_rate'] * 100:.1f}%")
                    st.metric("Warm Starts", gvisor_metrics['warm_starts'])
                    st.metric("Cold Starts", gvisor_metrics['cold_starts'])
                else:
                    st.info("No gVisor metrics available")
            
            # Get execution history
            executions = get_function_executions(selected_function_id)
            
            if executions:
                # Convert to DataFrame
                df = pd.DataFrame(executions)
                df['start_time'] = pd.to_datetime(df['start_time'])
                df['duration'] = pd.to_numeric(df['duration'])
                df['memory_used'] = pd.to_numeric(df['memory_used'])
                
                # Plot duration over time
                st.subheader("Duration Over Time")
                fig, ax = plt.subplots(figsize=(10, 5))
                
                # Group by virtualization
                for virt, group in df.groupby('virtualization'):
                    ax.scatter(group['start_time'], group['duration'], label=virt, alpha=0.7)
                
                ax.set_xlabel('Time')
                ax.set_ylabel('Duration (ms)')
                ax.legend()
                ax.grid(True, linestyle='--', alpha=0.7)
                
                st.pyplot(fig)
                
                # Plot memory usage over time
                st.subheader("Memory Usage Over Time")
                fig, ax = plt.subplots(figsize=(10, 5))
                
                # Group by virtualization
                for virt, group in df.groupby('virtualization'):
                    ax.scatter(group['start_time'], group['memory_used'], label=virt, alpha=0.7)
                
                ax.set_xlabel('Time')
                ax.set_ylabel('Memory Used (MB)')
                ax.legend()
                ax.grid(True, linestyle='--', alpha=0.7)
                
                st.pyplot(fig)

# System Stats page
elif page == "System Stats":
    st.title("System Statistics")
    
    # Compare virtualization technologies
    st.subheader("Virtualization Comparison")
    comparison = compare_virtualization()
    
    if comparison:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Docker")
            st.metric("Avg. Duration", f"{comparison['docker']['avg_duration_ms']:.2f} ms")
            st.metric("Avg. Memory Used", f"{comparison['docker']['avg_memory_used_mb']:.2f} MB")
            st.metric("Total Executions", comparison['docker']['total_executions'])
            st.metric("Errors", comparison['docker']['errors'])
        
        with col2:
            st.subheader("gVisor")
            st.metric("Avg. Duration", f"{comparison['gvisor']['avg_duration_ms']:.2f} ms")
            st.metric("Avg. Memory Used", f"{comparison['gvisor']['avg_memory_used_mb']:.2f} MB")
            st.metric("Total Executions", comparison['gvisor']['total_executions'])
            st.metric("Errors", comparison['gvisor']['errors'])
        
        # Create comparison chart
        st.subheader("Performance Comparison")
        
        # Duration comparison
        fig, ax = plt.subplots(figsize=(10, 5))
        technologies = ["Docker", "gVisor"]
        durations = [comparison['docker']['avg_duration_ms'], comparison['gvisor']['avg_duration_ms']]
        
        ax.bar(technologies, durations, color=['#1f77b4', '#ff7f0e'])
        ax.set_ylabel('Avg. Duration (ms)')
        ax.set_title('Average Execution Duration')
        ax.grid(True, linestyle='--', alpha=0.7, axis='y')
        
        st.pyplot(fig)
        
        # Memory comparison
        fig, ax = plt.subplots(figsize=(10, 5))
        memory_usage = [comparison['docker']['avg_memory_used_mb'], comparison['gvisor']['avg_memory_used_mb']]
        
        ax.bar(technologies, memory_usage, color=['#1f77b4', '#ff7f0e'])
        ax.set_ylabel('Avg. Memory Used (MB)')
        ax.set_title('Average Memory Usage')
        ax.grid(True, linestyle='--', alpha=0.7, axis='y')
        
        st.pyplot(fig)
    else:
        st.info("No comparison data available")
    
    # Get all functions
    functions = get_functions()
    
    if functions:
        st.subheader("Function Statistics")
        
        # Create DataFrame
        df = pd.DataFrame(functions)
        
        # Count by language
        language_counts = df['language'].value_counts()
        
        # Plot language distribution
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(language_counts, labels=language_counts.index, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        ax.set_title('Functions by Language')
        
        st.pyplot(fig)