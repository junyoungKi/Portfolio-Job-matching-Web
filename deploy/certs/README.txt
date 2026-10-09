Example filenames for the Cloudflare Origin Certificate (PEM). Both files are gitignored:

  origin.pem
  origin-key.pem

Create them in the Cloudflare dashboard (SSL/TLS → Origin Server) for
ai-job-matching.com and *.ai-job-matching.com. Do not commit the certificate
or the private key. Placement and deploy order are in the Deployment section
of README.md and README.ko.md.
