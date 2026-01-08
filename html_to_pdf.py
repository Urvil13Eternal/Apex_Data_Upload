from pyhtml2pdf import converter
import os
# sudo apt install wkhtmltopdf

def convert_html_to_pdf(html_file, pdf_file):
    converter.convert(
        f"file:///{html_file}",
        pdf_file,
        print_options={
            "paperWidth": 8.27,      # A4 width (inches)
            "paperHeight": 11.69,    # A4 height
            "marginTop": 0.4,
            "marginBottom": 0.4,
            "marginLeft": 0.4,
            "marginRight": 0.4,
            "scale": 0.95,           # IMPORTANT for wide tables
            "printBackground": True
        }
    )

    print("PDF generated:", pdf_file)

if __name__ == "__main__":
    html_file = os.path.abspath("test.html")
    pdf_file = os.path.abspath("test.pdf")
    convert_html_to_pdf(html_file, pdf_file)