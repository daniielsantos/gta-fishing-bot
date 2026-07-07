# Aplicar commit no gta-driving-bot (se o agente nao conseguiu dar push)

O commit ja esta pronto neste patch. No PowerShell:

```powershell
cd C:\Users\daniel\gta-driving-bot
git pull origin main
git am C:\Users\daniel\gta-fishing-bot\gta-driving-bot-planning\0001-docs-corrige-README-do-gta-driving-bot-planejamento-autonomo.patch
git push origin main
```

Se `git am` falhar, copie manualmente:

```powershell
Copy-Item C:\Users\daniel\gta-fishing-bot\gta-driving-bot-planning\README.md C:\Users\daniel\gta-driving-bot\ -Force
Copy-Item C:\Users\daniel\gta-fishing-bot\gta-driving-bot-planning\.gitignore C:\Users\daniel\gta-driving-bot\ -Force
Copy-Item C:\Users\daniel\gta-fishing-bot\gta-driving-bot-planning\requirements.txt C:\Users\daniel\gta-driving-bot\ -Force
cd C:\Users\daniel\gta-driving-bot
git add README.md .gitignore requirements.txt
git commit -m "docs: corrige README do gta-driving-bot (planejamento autonomo)"
git push origin main
```
