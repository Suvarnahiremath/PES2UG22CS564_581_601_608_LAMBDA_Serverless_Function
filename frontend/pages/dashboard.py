import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import datetime
import time

# API URL
API_URL = "http://localhost:8000/api"

st.set_page_config(
    page_title="Serverless Platform - Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("Monitoring Dashboard")

# Helper functions
def get_functions():
    response = requests.get(f"{API_URL}/functions/")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error fetching functions: {response.text}")
        return []

def get_executions():
    response = requests.get(f"{API_URL}/executions/")
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error fetching executions: {response.text}")
        return []

def get_function_metrics(function_id=None):
    url = f"{API_URL}/metrics/functions/{function_id}" if function_id else f"{API_URL}/metrics/compare"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error fetching metrics: {response.text}")
        return []

# Auto-refresh
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 5, 60, 10)

if auto_refresh:
    st.sidebar.write(f"Dashboard will refresh every {refresh_interval} seconds")

# Get data
functions = get_functions()
executions = get_executions()

# Convert executions to DataFrame
if executions:
    df_executions = pd.DataFrame(executions)
    df_executions['start_time'] = pd.to_datetime(df_executions['start_time'])
    df_executions['end_time'] = pd.to_datetime(df_executions['end_time'])
    df_executions['duration'] = pd.to_numeric(df_executions['duration'])
    df_executions['memory_used'] = pd.to_numeric(df_executions['memory_used'])
    df_executions['cpu_used'] = pd.to_numeric(df_executions['cpu_used'])

# System overview
st.header("System Overview")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Functions", len(functions))

with col2:
    if executions:
        st.metric("Total Executions", len(executions))
    else:
        st.metric("Total Executions", 0)

with col3:
    if executions:
        success_rate = len(df_executions[df_executions['status'] == 'success']) / len(df_executions) * 100
        st.metric("Success Rate", f"{success_rate:.1f}%")
    else:
        st.metric("Success Rate", "N/A")

with col4:
    if executions:
        avg_duration = df_executions['duration'].mean()
        st.metric("Avg. Duration", f"{avg_duration:.2f} ms")
    else:
        st.metric("Avg. Duration", "N/A")

# Virtualization comparison
st.header("Virtualization Comparison")

comparison = get_function_metrics()

if comparison and isinstance(comparison, dict) and 'docker' in comparison and 'gvisor' in comparison:
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
    
    # Create comparison charts
    col1, col2 = st.columns(2)
    
    with col1:
        # Duration comparison
        fig, ax = plt.subplots(figsize=(6, 4))
        technologies = ["Docker", "gVisor"]
        durations = [comparison['docker']['avg_duration_ms'], comparison['gvisor']['avg_duration_ms']]
        
        ax.bar(technologies, durations, color=['#1f77b4', '#ff7f0e'])
        ax.set_ylabel('Avg. Duration (ms)')
        ax.set_title('Average Execution Duration')
        ax.grid(True, linestyle='--', alpha=0.7, axis='y')
        
        st.pyplot(fig)
    
    with col2:
        # Memory comparison
        fig, ax = plt.subplots(figsize=(6, 4))
        memory_usage = [comparison['docker']['avg_memory_used_mb'], comparison['gvisor']['avg_memory_used_mb']]
        
        ax.bar(technologies, memory_usage, color=['#1f77b4', '#ff7f0e'])
        ax.set_ylabel('Avg. Memory Used (MB)')
        ax.set_title('Average Memory Usage')
        ax.grid(True, linestyle='--', alpha=0.7, axis='y')
        
        st.pyplot(fig)
else:
    st.info("No comparison data available")

# Recent executions
st.header("Recent Executions")

if executions:
    # Sort by start time
    df_recent = df_executions.sort_values('start_time', ascending=False).head(10)
    
    # Create a function name mapping
    function_names = {f['id']: f['name'] for f in functions}
    df_recent['function_name'] = df_recent['function_id'].map(lambda x: function_names.get(x, f"Function {x}"))
    
    # Display as table
    st.dataframe(
        df_recent[['function_name', 'start_time', 'status', 'virtualization', 'duration', 'memory_used']],
        use_container_width=True
    )
    
    # Plot executions over time
    st.subheader("Executions Over Time")
    
    # Group by hour
    df_executions['hour'] = df_executions['start_time'].dt.floor('H')
    hourly_counts = df_executions.groupby(['hour', 'virtualization']).size().unstack(fill_value=0)
    
    # Plot
    fig, ax = plt.subplots(figsize=(12, 6))
    hourly_counts.plot(ax=ax)
    ax.set_xlabel('Time')
    ax.set_ylabel('Number of Executions')
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.legend(title='Virtualization')
    
    st.pyplot(fig)
    
    # Plot duration distribution
    st.subheader("Duration Distribution")
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Group by virtualization
    for virt, group in df_executions.groupby('virtualization'):
        ax.hist(group['duration'], bins=20, alpha=0.5, label=virt)
    
    ax.set_xlabel('Duration (ms)')
    ax.set_ylabel('Frequency')
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.7)
    
    st.pyplot(fig)
else:
    st.info("No execution data available")

# Function-specific metrics
st.header("Function-Specific Metrics")

if functions:
    # Select function
    function_names = {f['id']: f['name'] for f in functions}
    selected_function_id = st.selectbox(
        "Select Function",
        options=list(function_names.keys()),
        format_func=lambda x: function_names[x]
    )
    
    # Get metrics for selected function
    function_metrics = get_function_metrics(selected_function_id)
    
    if function_metrics:
        # Group by virtualization
        docker_metrics = next((m for m in function_metrics if m["virtualization"] == "docker"), None)
        gvisor_metrics = next((m for m in function_metrics if m["virtualization"] == "gvisor"), None)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Docker")
            if docker_metrics:
                st.metric("Avg. Duration", f"{docker_metrics['avg_duration_ms']:.2f} ms")
                st.metric("Min Duration", f"{docker_metrics['min_duration_ms']:.2f} ms")
                st.metric("Max Duration", f"{docker_metrics['max_duration_ms']:.2f} ms")
                st.metric("Avg. Memory Used", f"{docker_metrics['avg_memory_used_mb']:.2f} MB")
                st.metric("Total Executions", docker_metrics['total_executions'])
                st.metric("Success Rate", f"{docker_metrics['success_rate'] * 100:.1f}%")
            else:
                st.info("No Docker metrics available")
        
        with col2:
            st.subheader("gVisor")
            if gvisor_metrics:
                st.metric("Avg. Duration", f"{gvisor_metrics['avg_duration_ms']:.2f} ms")
                st.metric("Min Duration", f"{gvisor_metrics['min_duration_ms']:.2f}  ms")
                st.metric("Min Duration", f"{gvisor_metrics['min_duration_ms']:.2f} ms")
                st.metric("Max Duration", f"{gvisor_metrics['max_duration_ms']:.2f} ms")
                st.metric("Avg. Memory Used", f"{gvisor_metrics['avg_memory_used_mb']:.2f} MB")
                st.metric("Total Executions", gvisor_metrics['total_executions'])
                st.metric("Success Rate", f"{gvisor_metrics['success_rate'] * 100:.1f}%")
            else:
                st.info("No gVisor metrics available")
        
        # Filter executions for this function
        if executions:
            function_executions = df_executions[df_executions['function_id'] == selected_function_id]
            
            if not function_executions.empty:
                # Plot duration over time
                st.subheader("Duration Over Time")
                fig, ax = plt.subplots(figsize=(12, 6))
                
                # Group by virtualization
                for virt, group in function_executions.groupby('virtualization'):
                    ax.scatter(group['start_time'], group['duration'], label=virt, alpha=0.7)
                
                ax.set_xlabel('Time')
                ax.set_ylabel('Duration (ms)')
                ax.legend()
                ax.grid(True, linestyle='--', alpha=0.7)
                
                st.pyplot(fig)
                
                # Plot memory usage over time
                st.subheader("Memory Usage Over Time")
                fig, ax = plt.subplots(figsize=(12, 6))
                
                # Group by virtualization
                for virt, group in function_executions.groupby('virtualization'):
                    ax.scatter(group['start_time'], group['memory_used'], label=virt, alpha=0.7)
                
                ax.set_xlabel('Time')
                ax.set_ylabel('Memory Used (MB)')
                ax.legend()
                ax.grid(True, linestyle='--', alpha=0.7)
                
                st.pyplot(fig)
            else:
                st.info("No execution data available for this function")
    else:
        st.info("No metrics available for this function")
else:
    st.info("No functions found")

# Auto-refresh
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()