# SPARK Tool [![DOI][(https://zenodo.org/badge/996198515.svg)](https://doi.org/10.5281/zenodo.16922908)](https://doi.org/10.5281/zenodo.17872407)  [![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
**System for Public Access to Research Knowledge** 

The [SPARK](https://wpo.noaa.gov/reach/) is a web-based open-science tool developed by NOAA’s Weather Program Office (WPO) to provide public access to project-level information on WPO-funded research.

SPARK serves as the entry point to WPO’s research portfolio, offering a transparent view of active and completed projects and providing a historical look at WPO’s R&D investments. The tool helps users understand what research WPO funds, where it occurs, and how it contributes to advancing NOAA’s mission.

SPARK transforms static project tables into an **interactive, searchable interface**, allowing users to:

- 🔍 Search projects by title, keyword, or award number.  
- 📁 Filter projects by division, program, funded year, research topic, associated forecast systems, and state.  
- ✨ View additional project information through a **pop-out drawer** with summaries of project descriptions, benefits, and transition details.  
- 📑 Connect seamlessly to the [REACH](https://part-wpo.github.io/reach-dashboard/) tool to explore related research outputs such as publications, datasets, and code.

## 📊 Data Sources

- Project metadata originates from nine **WPO Project Directories** (Smartsheet trackers) maintained by each program.  
- Directories are updated semi-annually during Semi-Annual Reviews and via Research Performance Progress Reports (RPPRs).  
- A consolidated **WPO Smartsheet Report** merges approved, externally shareable project data (e.g., title, award number, PI, keywords) into a single dataset.  
- A **Google Apps Script** retrieves this data through the Smartsheet API, cleans and normalizes it, and uploads the resulting CSV to this GitHub repository via the GitHub API.  
- The published CSV serves as the data source for SPARK, fetched dynamically when the web app loads.

## 🔄 End-to-End Data Workflow

### Step 0 – Entering & Updating Project Data
SPARK relies on accurate, up-to-date information in the **WPO Project Directory** (Smartsheet).  
Programs must enter details for new projects and keep records current throughout and beyond the award period.  
See the **Project Directory User Guide** for data entry best practices.

### Step 1 – Program Consolidation
All nine program directories are merged into a single **consolidated Smartsheet Report**, which serves as the data source for SPARK.

### Step 2 – Automated Data Retrieval
A **Google Apps Script** calls the Smartsheet API to pull the latest consolidated data.

### Step 3 – Data Cleaning & HTML Preparation
The Apps Script standardizes and enriches project data by:
- **Normalizing names and acronyms:** expands program names, extracts PI last names, and spells out partner acronyms (e.g., EMC → *Environmental Modeling Center*).  
- **Standardizing dates:** extracts *Year Funded* and formats *Period of Performance* as “Month YYYY – Month YYYY.”  
- **Cleaning multi-value fields:** converts newlines to comma-separated lists for keywords, hazards, states, and affiliations.  
- **Optimizing search:** builds a combined search field using lowercase text and normalized punctuation.  
- **Adding visuals:** inserts status and hazard icons for clear visual scanning.  
- **Linking outputs:** generates REACH links for projects with research outputs.  
- **Polishing text:** truncates long fields, fixes typographic characters, and ensures CSV/HTML safety.

### Step 4 – Automated CSV Upload
The cleaned dataset is uploaded via the **GitHub API** to this repository, updating the CSV file used by the live tool.

### Step 5 – Public Rendering
The SPARK interface is a **static HTML/JS app** hosted on GitHub Pages.  
- CSS defines the responsive layout, pop-out drawer, and accessibility styles.  
- On page load, the front-end fetches the CSV via GitHub’s Raw Content API.  
- **PapaParse.js** converts the CSV to JavaScript objects.  
- **Choices.js** powers multi-select dropdown filters.  
- Filtered results render as responsive rows; each opens a **drawer** with detailed project info and REACH links.

### Step 6 – Public Embedding
The live SPARK site is **embedded via iframe** on NOAA WPO’s public WordPress site, allowing users to explore projects without leaving the page.

## 🕒 Update & Refresh Process

- A **time-based trigger** runs automatically at the end of each quarter — December (Q1), March (Q2), June (Q3), September (Q4).  
- When triggered, the script:
  1. Calls the Smartsheet API to retrieve the latest consolidated data.  
  2. Cleans, formats, and enriches the dataset.  
  3. Uploads the new CSV to GitHub.  
- SPARK automatically fetches the newest CSV on next page load, ensuring users see the most current information.

## ⚙️ APIs, Libraries, and External Services

| Component | Purpose |
|------------|----------|
| **SmartsheetGov API** | Retrieves consolidated project metadata |
| **GitHub API** | Uploads updated CSV to public repository |
| **GitHub Raw Content API** | Serves the CSV for the SPARK front end |
| **PapaParse.js** | Parses CSV into JavaScript objects |
| **Choices.js** | Multi-select dropdowns for interactive filtering |
| **Material Icons** | Provides iconography for the interface |

## 🎨 UI/UX Features

- Keyword and text-based search across project titles, goals, and metadata.  
- Filter options by Program, Division, Funded Year, Project Status, Research Topic, State, and Forecast System/Model.  
- Quick-filter hazard icons (e.g., Severe Weather, Fire Weather, Winter Weather).  
- Pop-out project drawer with high-level summary, benefits, transition details, and PI info.  
- “View Outputs” button linking directly to related research in **REACH**.  
- Dynamic status and hazard icons to visually distinguish project activity and focus.  
- Responsive, accessible layout optimized for both desktop and mobile.

## 🚀 Hosting & Deployment

- **Static Hosting:** GitHub Pages  
- **Automated Pipeline:**
  1. WPO program staff update Project Directories  
  2. Consolidated Smartsheet Report merges metadata  
  3. Google Apps Script fetches via Smartsheet API  
  4. Script cleans and normalizes data  
  5. Script uploads CSV to GitHub via GitHub API  
  6. SPARK fetches CSV dynamically for public display  
  7. SPARK embedded on WPO WordPress site via iframe  

## ⚠️ Known Limitations

- SPARK depends on timely and accurate project-level data entry in the WPO Project Directory.  
- SPARK currently displays only WPO-funded projects and does not yet integrate data from other NOAA offices or partners.  
- Data rendering relies on GitHub-hosted CSV files, and API rate limits may affect large or frequent updates.

## 📜 License

© 2025 NOAA Weather Program Office (WPO).  
Released under the [Apache 2.0 License](LICENSE).

## 📬 Contact

For questions or feedback, please contact the **WPO Portfolio Analysis and Research Transitions (PART) Program** at:  
📧 **part.wpo@noaa.gov**  
🌐 [https://wpo.noaa.gov](https://wpo.noaa.gov/)

---
