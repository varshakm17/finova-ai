import json
import time
from backend.orchestration.graph import FinovaOrchestrationEngine
from backend.agents.agent_models import ReportGenerationRequest

engine = FinovaOrchestrationEngine()

companies = [
    {
        "ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "period": "FY2023",
        "question": "Analyze Microsoft FY2023 cloud revenue, operating performance, and profitability."
    },
    {
        "ticker": "TSLA",
        "company_name": "Tesla, Inc.",
        "period": "FY2023",
        "question": "Analyze Tesla FY2023 automotive gross margin, total revenues, and free cash flow."
    },
    {
        "ticker": "NVDA",
        "company_name": "NVIDIA Corporation",
        "period": "FY2024",
        "question": "Analyze NVIDIA FY2024 revenue growth, gross margin expansion, and capital allocation."
    }
]

results = []

for c in companies:
    print(f"\n==========================================")
    print(f"Running report for {c['ticker']} ({c['company_name']})...")
    req = ReportGenerationRequest(
        ticker=c["ticker"],
        question=c["question"],
        reporting_period=c["period"],
        company_name=c["company_name"]
    )
    t0 = time.time()
    resp = engine.run_report(req)
    dur = round(time.time() - t0, 2)
    
    print(f"Status: {resp.status}")
    print(f"Verification Status: {resp.verification_status}")
    print(f"Report ID: {resp.report_id}")
    print(f"Total sections: {resp.total_sections}")
    print(f"Evidence cited: {resp.total_evidence_cited}")
    print(f"Calculations cited: {resp.total_calculations_cited}")
    print(f"Execution time: {dur}s (engine reported {resp.execution_time_ms} ms)")
    if resp.warnings:
        print(f"Warnings ({len(resp.warnings)}):")
        for w in resp.warnings[:5]:
            print("  -", w)
    if resp.errors:
        print(f"Errors: {resp.errors}")
        
    results.append({
        "ticker": c["ticker"],
        "company_name": c["company_name"],
        "period": c["period"],
        "status": resp.status,
        "verification_status": resp.verification_status,
        "report_id": resp.report_id,
        "total_sections": resp.total_sections,
        "total_evidence_cited": resp.total_evidence_cited,
        "total_calculations_cited": resp.total_calculations_cited,
        "execution_time_s": dur,
        "warnings_count": len(resp.warnings) if resp.warnings else 0,
        "errors_count": len(resp.errors) if resp.errors else 0
    })

with open("reports/validation/multi_company_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nAll 3 company runs complete. Results written to reports/validation/multi_company_results.json")
