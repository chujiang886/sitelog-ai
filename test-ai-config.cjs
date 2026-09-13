const {chromium}=require('playwright'),{PNG}=require('pngjs'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.env.TEST_BASE,out=process.env.TEST_OUTPUT;
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('仅允许隔离配置验收');
let browser;
async function login(page,password){await page.locator('#login-user').fill('admin');await page.locator('#login-pass').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click()}
async function open(page){await page.evaluate(()=>Alpine.$data(document.body).openAdmin());await page.getByText('公司 AI 服务（管理员统一配置，可选）',{exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).companyAILoaded)}
async function save(page){await page.getByRole('button',{name:'验证并保存公司 AI 配置',exact:true}).click();await page.waitForFunction(()=>!Alpine.$data(document.body).authBusy)}
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/sitelog/');await login(page,'Test-admin-initial-12345');
 await page.locator('#password-current').fill('Test-admin-initial-12345');await page.locator('#password-next').fill('Test-admin-ready-12345');await page.locator('#password-confirm').fill('Test-admin-ready-12345');await page.getByRole('button',{name:'保存新密码',exact:true}).click();await page.locator('#login-user').waitFor({state:'visible'});await login(page,'Test-admin-ready-12345');await page.waitForFunction(()=>Alpine.$data(document.body).draftOwner===1);
 await open(page);assert.equal(await page.getByLabel('公司 AI 服务方',{exact:true}).locator('option').count(),15);
 assert.equal(await page.getByLabel('国内主流模型候选',{exact:true}).locator('option').count(),11);
 assert.equal(await page.getByLabel('公司 AI Key',{exact:true}).inputValue(),'');assert.equal(await page.getByLabel('视觉模型名称',{exact:true}).inputValue(),'HY-Vision-2.0-Instruct');
 await page.getByLabel('国内主流模型候选',{exact:true}).selectOption('deepseek-flash');assert.equal(await page.getByLabel('视觉模型名称',{exact:true}).inputValue(),'deepseek/deepseek-flash');await page.getByLabel('国内主流模型候选',{exact:true}).selectOption('MiniMax-M3');assert.equal(await page.getByLabel('视觉模型名称',{exact:true}).inputValue(),'minimax-m3');
 await page.getByLabel('公司 AI 服务方',{exact:true}).selectOption('custom');await page.getByLabel('服务商名称',{exact:true}).fill('公司兼容网关');await page.getByLabel('接口地址',{exact:true}).fill('https://gateway.example/v1');await page.getByLabel('公司 AI Key',{exact:true}).fill('isolated-custom-test');
 await page.getByRole('button',{name:'获取可用模型',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).availableAIModels.length===10);await page.getByLabel('服务商返回的模型',{exact:true}).selectOption('test-vision-model');await save(page);
 assert.ok(await page.evaluate(()=>Alpine.$data(document.body).aiConfigMessage.includes('已保存')));assert.equal(await page.getByLabel('公司 AI Key',{exact:true}).inputValue(),'');
 // 修改目标地址但留空密钥不能将原密钥发往新地址。
 await page.getByLabel('接口地址',{exact:true}).fill('https://other.example/v1');await save(page);assert.ok(await page.evaluate(()=>Alpine.$data(document.body).aiConfigMessage.includes('重新填写')));
 await page.getByLabel('接口地址',{exact:true}).fill('https://gateway.example/v1');await page.getByLabel('公司 AI Key',{exact:true}).fill('rejected-test-key');await save(page);assert.ok(await page.evaluate(()=>Alpine.$data(document.body).aiConfigMessage.includes('鉴权失败')));
 let current=await page.evaluate(()=>Alpine.$data(document.body).accountJSON('/admin/ai'));assert.equal(current.ai.model,'test-vision-model');assert.equal(current.ai.protocol,'openai');assert.ok(!('key' in current.ai));
 // 第二协议使用真实后端适配，模拟上游响应，成功后重复打开可恢复。
 await page.getByLabel('接口协议',{exact:true}).selectOption('anthropic');await page.getByLabel('接口地址',{exact:true}).fill('https://gateway.example/v1');await page.getByLabel('公司 AI Key',{exact:true}).fill('isolated-native-test');await page.getByLabel('视觉模型名称',{exact:true}).fill('test-native-vision');await save(page);
 assert.ok(await page.evaluate(()=>Alpine.$data(document.body).aiConfigMessage.includes('已保存')));
 await page.getByLabel('关闭管理员面板',{exact:true}).click();await page.evaluate(()=>Alpine.$data(document.body).openAdmin());await page.waitForFunction(()=>Alpine.$data(document.body).companyAILoaded);assert.equal(await page.getByLabel('视觉模型名称',{exact:true}).inputValue(),'test-native-vision');
 await page.getByLabel('公司 AI 服务方',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'多服务商配置.png')});
 await page.getByLabel('国内主流模型候选',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'国内模型与接口配置.png')});await page.getByLabel('关闭管理员面板',{exact:true}).click();
 const image=new PNG({width:64,height:64});image.data.fill(255);await page.locator('input[type=file][accept="image/*"]').first().setInputFiles({name:'合成测试.png',mimeType:'image/png',buffer:PNG.sync.write(image)});await page.locator('#images-container .node-block').waitFor();
 await page.getByRole('button',{name:'重分析',exact:true}).click();await page.getByRole('dialog',{name:'比较 AI 新建议'}).waitFor();await page.getByRole('button',{name:'采用新建议',exact:true}).click();await page.waitForFunction(()=>Alpine.$data(document.body).images[0].aiSource?.model==='test-native-vision');
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'多服务商验收.json'),JSON.stringify({passed:true,presets:15,modelCandidates:10,modelsLoaded:10,flows:['原配置回填无密钥','获取服务商模型','自定义模型保存','地址变更不复用密钥','验证失败保留原配置','原生 Messages 协议','重新打开配置','真实持久队列到编辑采用'],errors},null,2));console.log('多服务商配置、动态模型、失败回退、原生协议与编辑识别验收通过');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
