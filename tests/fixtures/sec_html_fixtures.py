"""HTML document fixtures representing statutory SEC EDGAR 10-K and 10-Q filings."""

SAMPLE_10K_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>UNITED STATES SECURITIES AND EXCHANGE COMMISSION Form 10-K</title>
    <style>
        .hidden { display: none; }
        .text { font-family: Times New Roman; }
    </style>
    <script>
        console.log("Analytics script that must be stripped");
    </script>
</head>
<body>
    <div class="hidden">Hidden non-content tracking snippet</div>

    <h1>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</h1>
    <h2>FORM 10-K ANNUAL REPORT FOR FISCAL YEAR ENDED SEPTEMBER 30, 2023</h2>

    <!-- TABLE OF CONTENTS (Should NOT be extracted as substantive section content) -->
    <div id="toc">
        <h3>TABLE OF CONTENTS</h3>
        <table>
            <tr><td>Item 1. Business</td><td>Page 4</td></tr>
            <tr><td>Item 1A. Risk Factors</td><td>Page 12</td></tr>
            <tr><td>Item 1B. Unresolved Staff Comments</td><td>Page 30</td></tr>
            <tr><td>Item 7. Management's Discussion and Analysis</td><td>Page 35</td></tr>
            <tr><td>Item 7A. Quantitative and Qualitative Disclosures</td><td>Page 50</td></tr>
            <tr><td>Item 8. Financial Statements</td><td>Page 55</td></tr>
        </table>
    </div>

    <hr/>

    <!-- SUBSTANTIVE ITEM 1 -->
    <div>
        <h2>PART I</h2>
        <h3>ITEM 1. BUSINESS</h3>
        <p>
            Apple Inc. designs, manufactures, and markets smartphones, personal computers,
            tablets, wearables, and accessories, and sells a variety of related services.
            The Company's fiscal year is the 52- or 53-week period that ends on the last Saturday of September.
            The Company manages its business primarily on a geographic basis.
        </p>
        <p>
            The Company's product offerings include iPhone, Mac, iPad, and Wearables, Home and Accessories.
            Services include Advertising, AppleCare, Cloud Services, Digital Content, and Payment Services.
        </p>
    </div>

    <!-- SUBSTANTIVE ITEM 1A -->
    <div>
        <h3>ITEM 1A. RISK FACTORS</h3>
        <p>
            The Company's business, reputation, results of operations, and financial condition are subject
            to multiple risks, including global economic conditions, supply chain disruptions, and intense competition.
        </p>
        <p>
            Global and regional economic conditions could materially adversely affect the Company.
            The Company's operations and performance depend significantly on global economic conditions.
            Uncertainty about global economic conditions poses a risk as consumers and businesses may postpone spending.
        </p>
        <table>
            <tr><th>Component Dependency</th><th>Risk Profile</th></tr>
            <tr><td>Semiconductors</td><td>Single-source supply constraints</td></tr>
            <tr><td>Display Modules</td><td>High manufacturing complexity</td></tr>
        </table>
        <p>
            The Company relies on single-source or limited-source suppliers for components, which subjects the Company
            to supply shortages and price fluctuations.
        </p>
    </div>

    <!-- ITEM 1B BOUNDARY -->
    <div>
        <h3>ITEM 1B. UNRESOLVED STAFF COMMENTS</h3>
        <p>None.</p>
    </div>

    <!-- SUBSTANTIVE ITEM 7 -->
    <div>
        <h2>PART II</h2>
        <h3>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS</h3>
        <p>
            Total net sales decreased 3% or $11.0 billion during 2023 compared to 2022, primarily driven by lower net sales
            of Mac and iPad, partially offset by an increase in Services net sales.
        </p>
        <p>
            Gross margin was $169.1 billion in 2023 compared to $170.8 billion in 2022. The gross margin percentage was
            44.1% compared to 43.3% in the prior year, primarily driven by favorable product mix and strength in Services.
        </p>
        <p>
            Operating income was $114.3 billion in 2023. We continue to generate strong operating cash flows and return capital
            to shareholders through dividends and share repurchases.
        </p>
    </div>

    <!-- SUBSTANTIVE ITEM 7A -->
    <div>
        <h3>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h3>
        <p>
            The Company's investment portfolio is subject to interest rate risk, credit risk, and foreign currency exchange risk.
            The Company manages these risks through diversification and financial derivative instruments.
        </p>
    </div>

    <!-- ITEM 8 BOUNDARY -->
    <div>
        <h3>ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA</h3>
        <p>Financial statements follow.</p>
    </div>
</body>
</html>
"""

SAMPLE_10Q_HTML = """<!DOCTYPE html>
<html>
<head><title>Form 10-Q Quarterly Report</title></head>
<body>
    <h1>FORM 10-Q</h1>
    
    <h2>PART I — FINANCIAL INFORMATION</h2>
    <h3>ITEM 1. FINANCIAL STATEMENTS</h3>
    <p>Consolidated Condensed Balance Sheets and Statements of Operations.</p>

    <h3>ITEM 2. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS</h3>
    <p>
        Net sales were $81.8 billion for the three months ended July 1, 2023, down 1% from the prior year quarter.
        Services revenue grew 8% reaching a new all-time quarterly record of $21.2 billion.
        Operating expenses increased due to investments in research and development.
    </p>

    <h3>ITEM 3. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h3>
    <p>
        There have been no material changes to the market risk disclosures reported in the Company's Annual Report on Form 10-K.
    </p>

    <h2>PART II — OTHER INFORMATION</h2>
    <h3>ITEM 1A. RISK FACTORS</h3>
    <p>
        There have been no material changes from the risk factors previously disclosed in the Company's Annual Report on Form 10-K.
    </p>

    <h3>ITEM 6. EXHIBITS</h3>
    <p>Exhibits index.</p>
</body>
</html>
"""

SAMPLE_INLINE_XBRL_HTML = """<!DOCTYPE html>
<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
<body>
    <h3>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h3>
    <p>
        Our total revenue was <ix:nonFraction name="us-gaap:Revenues" unitRef="USD" scale="6">383,285</ix:nonFraction> million.
        This reflected strong execution across our <ix:nonNumeric name="us-gaap:SegmentDescription">Services</ix:nonNumeric> segment.
    </p>
    <h3>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES</h3>
    <p>Market risk disclosures.</p>
</body>
</html>
"""
