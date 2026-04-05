import { render } from 'preact'
import { App } from './app.jsx'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'

render(<App />, document.getElementById('app'))
