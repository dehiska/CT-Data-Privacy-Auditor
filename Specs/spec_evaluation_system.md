# Specification: Evaluation System for CT Data Privacy Auditor

---

## 1. Overview

This specification outlines the integration of an **evaluation system** into the CT Data Privacy Auditor project. The system will use **Ragas** and **DeepEval** to assess agent performance, data quality, and compliance accuracy. The goal is to ensure that synthetic data is representative and that agents produce faithful, relevant, and precise outputs.

---

## 2. Objectives

- Evaluate the quality of synthetic data by comparing agent performance on synthetic vs. real data.
- Assess agent outputs for **faithfulness**, **relevance**, and **context precision**.
- Define and track custom metrics for **violation detection**, **PII detection**, and **policy compliance**.

---

## 3. Tools and Frameworks

### 3.1 Ragas

- **Purpose**: Evaluate agent outputs for faithfulness, answer relevance, and context precision.
- **Adaptation**: While Ragas is designed for RAG systems, its metrics will be adapted to assess agent outputs in the multi-agent workflow.
- **Metrics**:
  - **Faithfulness**: Ensure compliance reports align with input data and CTDPA rules.
  - **Answer Relevance**: Assess if agent findings are relevant to the audit task.
  - **Context Precision**: Verify if agents use the correct context (e.g., policy clauses, PII types).
- **Implementation**:
  - Integrate Ragas into the evaluation pipeline to score agent outputs.
  - Use Ragas' `Dataset` and `Evaluation` modules to compare agent outputs against ground truth.

### 3.2 DeepEval

- **Purpose**: Provide a broader evaluation framework for agent performance, including custom metrics.
- **Metrics**:
  - **Violation Detection Accuracy**: % of correctly identified violations.
  - **PII Detection Precision/Recall**: False positives/negatives in PII detection.
  - **Policy Compliance Score**: % of policy clauses correctly matched to CTDPA rules.
- **Implementation**:
  - Use DeepEval's `TestCase` and `Evaluator` to define and run custom tests.
  - Implement assertions to validate agent outputs against expected results.

---

## 4. Evaluation Workflow

### 4.1 Data Preparation

- **Synthetic Data**: Use existing synthetic datasets (`business_data.csv`, `request_log.csv`, `business_policy.txt`).
- **Real Data**: If available, use real datasets for comparison. If not, create a small, manually validated dataset for ground truth.

### 4.2 Agent Performance Testing

- **Process**:
  1. Run agents on both synthetic and real data.
  2. Collect outputs (e.g., compliance reports, PII detection results).
  3. Compare performance metrics (precision, recall, F1-score) between synthetic and real data.
  4. Flag significant discrepancies for further investigation.
- **Expected Outcome**:
  - If performance differs significantly, refine synthetic data generation to better match real-world distributions.

### 4.3 Custom Metrics

- **Violation Detection Accuracy**:
  - Calculate as:
    ```
    (True Positives + True Negatives) / Total Cases
    ```
- **PII Detection Precision/Recall**:
  - **Precision**: `True Positives / (True Positives + False Positives)`
  - **Recall**: `True Positives / (True Positives + False Negatives)`
- **Policy Compliance Score**:
  - Calculate as:
    ```
    (Correctly Matched Clauses) / Total Clauses
    ```

---

## 5. Integration Steps

### 5.1 Setup

- Install Ragas and DeepEval:
  ```bash
  pip install ragas deepeval
  ```

### 5.2 Evaluation Script

- Create a script (`evaluate_agents.py`) to:
  - Load synthetic and real data.
  - Run agents and collect outputs.
  - Calculate and log metrics using Ragas and DeepEval.

### 5.3 Automated Testing

- Use `pytest` to automate evaluation:
  ```python
  import pytest
  from deepeval import assert_test
  from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric

  def test_agent_faithfulness():
      faithfulness_metric = FaithfulnessMetric()
      assert_test(agent_output, expected_output, [faithfulness_metric])
  ```

### 5.4 Reporting

- Generate evaluation reports (e.g., JSON, Markdown) summarizing:
  - Performance metrics.
  - Discrepancies between synthetic and real data.
  - Recommendations for improvement.

---

## 6. Expected Deliverables

- Evaluation script (`evaluate_agents.py`).
- Automated test suite for agent performance.
- Evaluation reports for each audit run.
- Documentation on how to interpret and act on evaluation results.
