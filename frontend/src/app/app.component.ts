import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: '<router-outlet />'
})
export class AppComponent {

  constructor(private translate: TranslateService) {
  this.translate.setDefaultLang('fr');
  this.translate.use('fr');
}
}
