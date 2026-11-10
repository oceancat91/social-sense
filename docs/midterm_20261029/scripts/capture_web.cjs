const { chromium }=require('C:/Users/32002/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');const path=require('path');
(async()=>{
 const root=path.resolve(__dirname,'..'); const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});
 const log=[];
 for(const [name,url] of [['local_archive','http://127.0.0.1:3186/app/']]){
  try {const response=await page.goto(url,{waitUntil:'networkidle',timeout:45000});
   await page.waitForTimeout(12000);
   await page.locator('#skip').click({timeout:45000});
   await page.waitForTimeout(3500);
   await page.screenshot({path:path.join(root,'evidence',name+'.png'),fullPage:true});
   fs.writeFileSync(path.join(root,'evidence',name+'.txt'),await page.locator('body').innerText());
   log.push({name,url,finalUrl:page.url(),status:response.status(),title:await page.title(),links:await page.locator('a').evaluateAll(es=>es.map(e=>({text:e.innerText,href:e.href}))),capturedAt:new Date().toISOString()});
   await page.keyboard.press('Enter');
   await page.waitForTimeout(10000);
   await page.screenshot({path:path.join(root,'evidence/local_detail.png'),fullPage:true});
   fs.writeFileSync(path.join(root,'evidence/local_detail.txt'),await page.locator('body').innerText());
  }catch(e){log.push({name,url,error:e.message});}
 }
 fs.writeFileSync(path.join(root,'evidence/local_capture.json'),JSON.stringify(log,null,2));
 console.log(JSON.stringify(log,null,2));await browser.close();
})();
