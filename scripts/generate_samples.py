"""Recreate the two optional synthetic upload samples (requires dev dependencies)."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from docx import Document
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'sample_documents'

def main():
    pdf = canvas.Canvas(str(OUT / 'finance_Q4.pdf'), pagesize=(595,842))
    pdf.setTitle('Synthetic Q4 financial report')
    pdf.setAuthor('Northstar synthetic assessment fixtures')
    pdf.setFillColor(HexColor('#203c34'));pdf.rect(0, 745,595,97,fill=1,stroke=0)
    pdf.setFillColor(HexColor('#e9f0e0'));pdf.setFont('Helvetica',10);pdf.drawString(48,803,'NORTHSTAR STUDIO / SYNTHETIC BUSINESS DATA')
    pdf.setFont('Times-Roman',25);pdf.drawString(48,768,'Quarterly financial report')
    pdf.setFillColor(HexColor('#293e2c'));pdf.setFont('Helvetica',12)
    lines=['Period: 2026-Q4','Currency: AED','Revenue: 1,500,000','Cost of goods sold: 810,000','Operating expenses: 340,000','Cash balance: 720,000','Monthly net burn: 120,000','Reported gross margin: 46%']
    y=692
    for line in lines:pdf.drawString(48,y,line);y-=35
    pdf.setFont('Helvetica',10)
    for line in ['Scope: Whole company, standalone quarter, amounts in full currency units.','All figures are synthetic assessment data.','Monthly net burn is a separate cash-flow measure, not operating profit.','Expected code results: gross margin 46%; operating profit AED 350,000.']:
        pdf.drawString(48,y-20,line);y-=25
    pdf.setFillColor(HexColor('#849276'));pdf.setFont('Helvetica',9);pdf.drawString(48,55,'Upload as Finance / Shared to demonstrate the ingestion workflow.');pdf.save()
    doc=Document(); sec=doc.sections[0];sec.top_margin=Inches(.85);sec.bottom_margin=Inches(.8)
    from docx.oxml.ns import qn
    for style in doc.styles:
        for border in list(style.element.iter(qn('w:pBdr'))):
            border.getparent().remove(border)
    style=doc.styles['Normal'];style.font.name='Calibri';style.font.size=Pt(11);style.paragraph_format.space_after=Pt(12)
    title=doc.add_paragraph('Travel and training policy','Title');title.runs[0].font.color.rgb=RGBColor(0,0,0)
    doc.add_paragraph('Northstar Studio uses this synthetic policy to demonstrate Word document upload and evidence retrieval. All amounts and rules below are fictional.')
    doc.add_paragraph('Effective date: 2026-10-01')
    doc.add_paragraph('Travel allowance: AED 300 per approved overnight business trip.')
    doc.add_paragraph('Training budget: AED 2,000 per employee per year with manager approval.')
    doc.add_paragraph('Receipt deadline: Submit expense receipts within 10 calendar days of returning.')
    doc.add_paragraph('Approval process')
    doc.add_paragraph('Employees must obtain manager approval before booking travel or committing to a training course. Finance records the approved expense after receiving the receipt.')
    doc.add_paragraph('Upload as HR / Management and Shared to make this document available to both demonstration accounts.')
    doc.core_properties.author='Northstar synthetic assessment fixtures';doc.core_properties.title='Travel and training policy'
    doc.save(OUT/'travel_training_policy.docx')

if __name__=='__main__':main()
