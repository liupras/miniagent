1. ERR_PNPM_IGNORED_BUILDS

~~~
pnpm approve-builds
~~~

2. 'NODE_OPTIONS' 不是内部或外部命令，也不是可运行的程序 或批处理文件

~~~
pnpm add -D cross-env
~~~
找到：
~~~
"scripts": {
  "dev": "NODE_OPTIONS=--max-old-space-size=4096 vite"
}
~~~
改成：
~~~
"scripts": {
  "dev": "cross-env NODE_OPTIONS=--max-old-space-size=4096 vite"
}
~~~

3. install其它

~~~
pnpm add vue-demi
pnpm add tippy.js
~~~

4. 更新

~~~
npx update-browserslist-db@latest
pnpm update
~~~